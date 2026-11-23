"""Export the game's map art as WebP for the tracker prototype (one-time build step; numpy + Pillow, both installed).

  field maps    UI/CustomTex/Map/Field/<Level>_NN            -> cache/maps/<Level>_NN.webp
  dungeon floor UI/CustomTex/Map/Dungeon/<Dungeon>_<F>_Back + _Main (or _State00_Main)
                                                             -> cache/maps/<Dungeon>_<F>.webp (Back under Main)
  world map     Common bntx MapTexWorldAll_00                -> cache/maps/World.webp
  map icons     Common bntx MapIcon*                         -> cache/icons/<name>.png

Run:  python tracker/research/build_maps.py [--scale 0.5] [--out DIR] [--only KokiriForest_Child_00 InsideTheDekuTree_B1 ...]

The map art is kept per scale: --scale 0.5 (the prototype's half size) in cache/maps, the game's native 2000x1440
(--scale 1, what the tracker app shows) in cache/maps_full, any other scale in cache/maps_<scale>; --out overrides.
"""
import glob
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bntx  # noqa: E402

MAPS = os.path.join(bntx.ROMFS, "UI/CustomTex/Map")
FLOORS = ("B4", "B3", "B2", "B1", "1F", "2F", "3F", "4F", "5F")


def jobs():
    out = {}
    for p in sorted(glob.glob(os.path.join(MAPS, "Field", "*.bntx.zs"))):
        n = os.path.basename(p).split(".")[0]
        if not n.startswith("Mini_"):
            out[n] = [f"Field/{n}"]
    by_floor = {}
    for p in sorted(glob.glob(os.path.join(MAPS, "Dungeon", "*.bntx.zs"))):
        n = os.path.basename(p).split(".")[0]
        parts = n.split("_")
        if len(parts) >= 3 and parts[1] in FLOORS:
            by_floor.setdefault(f"{parts[0]}_{parts[1]}", []).append(n)
    for floor, names in by_floor.items():
        back = [n for n in names if n.endswith("_Back")]
        back = [n for n in back if n == f"{floor}_Back"] or sorted(back)[:1]
        main = [n for n in names if n.endswith("_Main")]
        # One Main layer, the plain one or else the first variant (State00 is before the floor's puzzle/event,
        # Lv1 is the Water Temple's lowest water level). The tracker would offer the others as a toggle.
        main = [n for n in main if n == f"{floor}_Main"] or sorted(main)[:1]
        out[floor] = [f"Dungeon/{n}" for n in back + main]
    return out


def cache_dir(scale):
    """The cache folder for one scale of the map art. Each scale gets its own, so a half-size map is never reused."""
    if abs(scale - 0.5) < 1e-6:
        return os.path.join(HERE, "cache", "maps")
    if abs(scale - 1.0) < 1e-6:
        return os.path.join(HERE, "cache", "maps_full")
    return os.path.join(HERE, "cache", f"maps_{scale:g}")


def main(argv):
    from PIL import Image
    scale = float(argv[argv.index("--scale") + 1]) if "--scale" in argv else 0.5
    dst = argv[argv.index("--out") + 1] if "--out" in argv else cache_dir(scale)
    only = argv[argv.index("--only") + 1:] if "--only" in argv else None
    # full size is nearly lossless since the tracker re-encodes it once as JPEG, smaller sizes keep the lower quality
    quality = 95 if scale >= 1 else 85
    fs = bntx.romfs()
    os.makedirs(dst, exist_ok=True)
    for name, layers in jobs().items():
        if only and name not in only:
            continue
        p = os.path.join(dst, name + ".webp")
        if os.path.exists(p):
            continue
        t0 = time.time()
        im = Image.new("RGBA", (2000, 1440), (0, 0, 0, 0))
        for rel in layers:
            t = bntx.textures(fs.read(f"UI/CustomTex/Map/{rel}.bntx.zs"))[0]
            layer = Image.fromarray(bntx.decode(t), "RGBA")
            if layer.size != (2000, 1440):
                layer = layer.resize((2000, 1440), Image.LANCZOS)
            im.alpha_composite(layer)
        if abs(scale - 1.0) > 1e-6:
            im = im.resize((int(2000 * scale), int(1440 * scale)), Image.LANCZOS)
        im.save(p, quality=quality, method=4)
        print(f"{name}: {len(layers)} layer(s), {time.time() - t0:.1f}s", flush=True)
    if not only or "World" in only:
        common = {t["name"]: t for t in bntx.textures(fs.read(
            "UI/Layout2Archive/Common.Product.100.Nin_Ounce_NVN2.bntx.zs"))}
        p = os.path.join(dst, "World.webp")
        if not os.path.exists(p):
            Image.fromarray(bntx.decode(common["MapTexWorldAll_00"]), "RGBA").resize((2304, 1680), Image.LANCZOS) \
                .save(p, quality=quality)
        idst = os.path.join(HERE, "cache", "icons")
        os.makedirs(idst, exist_ok=True)
        for n, t in common.items():
            if n.startswith(("MapIcon", "OcarinaMelodyIcon")) and "Sh_" not in n and not n.endswith("Sh_00"):
                q = os.path.join(idst, n + ".png")
                if not os.path.exists(q):
                    Image.fromarray(bntx.decode(t), "RGBA").save(q)


if __name__ == "__main__":
    main(sys.argv[1:])
