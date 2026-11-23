"""Checks that every pin of a seed's tracker.json sits on its map's art and not on the dark frame around it.

  python tracker/research/check_pins.py out/seed1 out/seed2 [--near N] [--glow]

The art is whatever the map JPG (tracker/dist/data/maps/<map>.jpg) shows apart from its frame. The frame is the
flat (46, 32, 20) brown build_data.py pastes the art on, reached from the image border, so the art's own dark spots
inside it stay art. A pin is off when its centre is on the frame. --near N also lists pins within N map pixels of
the frame. --glow lists pins in the soft dark glow around the art: not on a frame pixel, but the 9x9 pixels around
it are on average nearer the frame's colour than 30, so they look off the map. Exits with status 1 when a pin is
off the art.
"""
import json
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
MAPS = os.path.join(ROOT, "tracker", "dist", "data", "maps")
FRAME = (46, 32, 20)
_MASKS = {}
_FAR = {}


def art_mask(map_id):
    """bool [H, W]: True on the art."""
    if map_id in _MASKS:
        return _MASKS[map_id]
    a = np.asarray(Image.open(os.path.join(MAPS, map_id + ".jpg")).convert("RGB")).astype(np.int16)
    _FAR[map_id] = np.abs(a - np.array(FRAME, dtype=np.int16)).max(axis=2)
    frame = _FAR[map_id] <= 12
    out = np.zeros_like(frame)
    out[0, :], out[-1, :], out[:, 0], out[:, -1] = frame[0, :], frame[-1, :], frame[:, 0], frame[:, -1]
    while True:  # grow the frame mask in four directions from the image border until it stops changing
        g = out.copy()
        g[1:, :] |= out[:-1, :]
        g[:-1, :] |= out[1:, :]
        g[:, 1:] |= out[:, :-1]
        g[:, :-1] |= out[:, 1:]
        g &= frame
        if (g == out).all():
            break
        out = g
    _MASKS[map_id] = ~out
    return _MASKS[map_id]


def frame_distance(mask, x, y, limit):
    """Map pixels from (x, y) to the nearest frame pixel, up to limit (limit + 1 when none that close)."""
    h, w = mask.shape
    xi, yi = int(round(x)), int(round(y))
    if not (0 <= xi < w and 0 <= yi < h) or not mask[yi, xi]:
        return 0
    x0, x1, y0, y1 = max(0, xi - limit), min(w, xi + limit + 1), max(0, yi - limit), min(h, yi + limit + 1)
    sub = ~mask[y0:y1, x0:x1]
    if not sub.any():
        return limit + 1
    ys, xs = np.nonzero(sub)
    return float(np.sqrt(((xs + x0 - xi) ** 2 + (ys + y0 - yi) ** 2).min()))


def in_glow(map_id, x, y):
    far = _FAR[map_id]
    xi, yi = int(round(x)), int(round(y))
    return float(far[max(0, yi - 4):yi + 5, max(0, xi - 4):xi + 5].mean()) < 30


def check(path, near=0):
    t = json.load(open(path, encoding="utf-8"))
    k = t.get("map_scale", 0.5)  # same rule as the app, seeds without it were made at half size
    off, close, glow = [], [], []
    for c in t["checks"]:
        if "map" not in c:
            continue
        m = art_mask(c["map"])
        x, y = c["x"] / k, c["y"] / k
        d = frame_distance(m, x, y, max(near, 1))
        if d == 0:
            off.append((c["map"], c["name"], x, y))
            continue
        if near and d <= near:
            close.append((c["map"], c["name"], x, y, d))
        if in_glow(c["map"], x, y):
            glow.append((c["map"], c["name"], x, y))
    return t, off, close, glow


def main(argv):
    near = int(argv[argv.index("--near") + 1]) if "--near" in argv else 0
    dirs = [a for i, a in enumerate(argv) if not a.startswith("--") and (i == 0 or argv[i - 1] != "--near")]
    bad = 0
    for d in dirs:
        p = d if d.endswith(".json") else os.path.join(d, "tracker.json")
        t, off, close, glow = check(p, near)
        n = sum(1 for c in t["checks"] if "map" in c)
        print(f"{p}: {n} pins, {len(off)} off the art, {len(glow)} in the glow around it"
              + (f", {len(close)} within {near} px of the frame" if near else ""))
        for m, name, x, y in sorted(off):
            print(f"  OFF   {m:32s} {name}  ({x:.0f}, {y:.0f})")
        for m, name, x, y in sorted(glow) if "--glow" in argv else ():
            print(f"  glow  {m:32s} {name}  ({x:.0f}, {y:.0f})")
        for m, name, x, y, dd in sorted(close):
            print(f"  near  {m:32s} {name}  ({x:.0f}, {y:.0f}) {dd:.1f} px")
        bad += len(off)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
