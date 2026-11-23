"""Read-back of starting_hearts other than 3 (tools/rando/world_settings.py, parity/_gaps_check.py READERS
"starting_hearts"). In the patch the new file's PlayerStatus.Life and MaxLife have to be 4 x the hearts. Those are
Sequence/SetPouchAndStatusForGameStart's two i32 constants, in quarter hearts, vanilla 12. A start below 3 has to
have added 3 - n Heart Containers to the pool in place of junk (world_settings.add_heart_containers), and the note
records the items it replaced."""
import os
import struct
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(HERE, "tools"))


def verify(patch, note, romfs):
    from romtools import Romfs
    bad = []
    hearts = note.get("hearts")
    if not isinstance(hearts, int) or not 1 <= hearts <= 20:
        return [f"starting hearts {hearts!r} is not 1-20"]
    fs = Romfs(romfs, os.path.join(HERE, "original"), [patch])
    data = fs.raw(note["file"])
    try:
        data = fs.zs.decompress(data)
    except Exception:  # noqa: BLE001  (stored uncompressed)
        pass
    for off in note.get("offsets") or []:
        got = struct.unpack_from("<i", data, off)[0]
        if got != 4 * hearts:
            bad.append(f"{note['file']} @{off:#x}: {got} quarter hearts, want {4 * hearts} ({hearts} hearts)")
    if len(note.get("offsets") or []) != 2:
        bad.append(f"{note['file']}: Life and MaxLife not both written ({note.get('offsets')})")
    want = max(3 - hearts, 0)
    if note.get("containers_added") != want or len(note.get("replaced") or []) != want:
        bad.append(f"{hearts} starting hearts: {note.get('containers_added')} Heart Containers added for "
                   f"{note.get('replaced')}, want {want}")
    return bad
