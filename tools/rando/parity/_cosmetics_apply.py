"""Apply a plan's "cosmetics" section to a built patch: run after tools/make_patch.py, before installing.

usage: python tools/rando/parity/_cosmetics_apply.py ROMFS PATCH_DIR PLAN.json [PLAN2.json ...]
       python tools/rando/parity/_cosmetics_apply.py ROMFS PATCH_DIR PLAN.json --check   (read the patch back: its
       bytes, then verify() below: the music graph and every sound's pool)

make_patch.py writes the same edits through build() below. This step writes them into PATCH_DIR again, same bytes,
the way make_patch.py does. It always starts from the vanilla file (./original copies win over the live romfs),
compresses with the same dictionary and keeps the vanilla copy in ./original for tools/install.py. The app doesn't
run that part anymore, only --check, which reads back what make_patch wrote. Every edit is in place (same size), so
the resource size table needs no change.

"cosmetics" section (written by tools/rando/parity/cosmetics.py):
  "slink":    [{"user", "key", "asset", "was"}]   sound link: the key plays `asset` instead of `was`
                                                  (SLink2/slink2.Product.111.bslnk.zs); [{"remap": {was: asset}}]
                                                  every key playing `was` (remake_shuffle_all_sfx). Music keys
                                                  re-pointed at whole tracks also edit the music graph
                                                  (Sound/Bgm/bgm.Product.111.byml.zs: _cosmetics_bgm)
  "textures": [{"file": "Tex/X.bntx.zs", "colour": "#RRGGBB", "ref": "Tex/Y.bntx.zs"}]   texture recoloured in
              place: with "ref", its green only at its brightness against Y's mean (BC1/BC3/ASTC,
              _cosmetics_tex.tunic_map); with "select" too, the named part instead of the green (the Goron/Zora
              tunics' cloth, the gauntlets' metal, the mirror shield's frame: _cosmetics_tex.SELECTIONS, against
              the mean of that part of Y); without either, all of it (BC1/BC3)
  "effects":  [{"file": "Effect/X.vsetb.byml.zs", "sets": [...], "emitters": regex, "entries": ["P80", ...],
                "colour": "#RRGGBB"}]             particle effect colours rewritten in place (_cosmetics_vfx)
  "hud":      [...]                               HUD textures and layout colours (_cosmetics_hud)
  "map_icons": [key, ...]                         the map tracker's icons added to the UI's texture and layout
                                                  archives (_map_icons: they grow, make_patch raises their sizes)
  "log":      {...}                               what was chosen (not applied)
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(HERE, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from romtools import Romfs  # noqa: E402
import _cosmetics_slink as S  # noqa: E402
import _cosmetics_bgm as B  # noqa: E402
import _cosmetics_tex as T  # noqa: E402
import _cosmetics_vfx as V  # noqa: E402

VANILLA = os.environ.get("REMAKE_ORIGINAL") or os.path.join(HERE, "original")  # the app: next to the game


KINDS = ("slink", "textures", "effects", "hud", "map_icons")


def load(paths):
    out = {k: [] for k in KINDS}
    for p in paths:
        c = json.load(open(p, encoding="utf-8")).get("cosmetics") or {}
        for k in KINDS:
            out[k] += c.get(k, [])
    return out


def build(romfs, cos):
    """{romfs path: new decompressed bytes} for the cosmetics edits."""
    fs = Romfs(romfs, VANILLA)
    files = {}
    if cos["slink"]:
        old = fs.read(S.SLINK)
        files[S.SLINK] = S.repoint(old, cos["slink"])
        bgm = B.build(fs, old, files[S.SLINK])  # so a whole track can finish in a fixed-length slot
        if bgm is not None:
            files[B.BGM] = bgm
    by_file = {}
    for op in cos["textures"]:
        by_file[op["file"]] = op  # the last recolour wins
    refs = {}
    for rel, op in sorted(by_file.items()):
        if op.get("select"):  # one part of the texture, by hue and by area where needed (_cosmetics_tex.SELECTIONS)
            key = (op["ref"], op["select"])
            if key not in refs:
                refs[key] = T.mean_of_selection(fs.read(op["ref"]), op["select"])[1]
            files[rel] = T.recolour_selected(fs.read(rel), op["select"], T.hex_rgb(op["colour"]), refs[key])[0]
        elif op.get("ref"):  # a tunic part, its green goes to the colour at its brightness against the reference's mean
            if op["ref"] not in refs:
                refs[op["ref"]] = T.mean_colour(fs.read(op["ref"]))[1]
            files[rel] = T.recolour_any(fs.read(rel), T.tunic_map(T.hex_rgb(op["colour"]), refs[op["ref"]]))[0]
        else:
            files[rel] = T.recolour(fs.read(rel), T.hex_rgb(op["colour"]))
    fx = {}
    for op in cos.get("effects", []):
        fx.setdefault(op["file"], []).append(op)
    for rel, groups in sorted(fx.items()):  # particle effect colours (_cosmetics_vfx), in order so a later one wins
        files[rel] = V.recolour(fs.read(rel), groups)[0]
    if cos.get("hud"):  # HUD textures and layout colours (_cosmetics_hud)
        import _cosmetics_hud as H
        files.update(H.build(fs, cos["hud"]))
    if cos.get("map_icons"):  # on top of the HUD's edits to the same two files
        import _map_icons as M
        files.update(M.build(fs, files))
    return fs, files


SOUND = os.path.join(HERE, "data", "rando", "cosmetics_sound.json")


def _pools(d):
    """{(user, key, sound it plays now): (pool name, allowed new sounds)} for every sound-link row a plan may change,
    from data/rando/cosmetics_sound.json (_cosmetics_build). Allowed is None when the row is checked by kind instead
    (sfx)."""
    blank = {S.BLANK}
    sources = ({r["track"] for r in d["bgm_area_slots"]} | {e["track"] for e in d["bgm_extra_tracks"]}
               | {g["group"] for g in d.get("bgm_event_groups", []) if g["group"] != "BGM_Shop"})
    fan = d["fanfares"] + d.get("jingles", [])
    out = {}
    for r in d["bgm_area_silence"]:
        out[(r["user"], r["key"], r["was"])] = ("music", sources | blank)
    for lp in d.get("bgm_area_layered", []):
        for r in lp["play"]:
            out[(r["user"], r["key"], r["was"])] = ("music", sources | blank)
        for r in lp["silence"]:
            out[(r["user"], r["key"], r["was"])] = ("music, silenced", blank)
    for ov in d.get("bgm_overlays", []):
        for r in ov["silence"]:
            out[(r["user"], r["key"], r["was"])] = ("music overlay, silenced", blank)
    for g in d.get("bgm_event_groups", []):
        for r in g["rows"]:
            out[(r["user"], r["key"], r["was"])] = ("event music", sources | blank)
    for r in d["bgm_area_slots"]:
        out[(r["user"], r["key"], r["track"])] = ("music", sources | blank)
    tracks = {r["track"] for r in fan}
    for f in fan:
        for r in [f] + f.get("also", []):
            out[(r["user"], r["key"], f["track"])] = ("fanfare", tracks | blank)
    songs = {r["track"] for r in d["ocarina_songs"]}
    for r in d["ocarina_songs"]:
        out[(r["user"], r["key"], r["track"])] = ("ocarina song", songs | blank)
    for r in d["ocarina_notes"]:
        out[(r["user"], r["key"], r["was"])] = ("ocarina note", {r["flute"]})
    for rows in d["link_voice"].values():
        for r in rows:
            out[(r["user"], r["key"], r["was"])] = ("Link's voice", blank)
    for n in ("0000", "0005", "0010"):
        out[(f"Event_Dm_StaffCredit_{n}", "SoundTrack", f"Dm_StaffCredit_{n}")] = ("credits", sources)
    for rows in d["sfx"].values():
        for r in rows:
            out[(r["user"], r["key"], r["was"])] = ("sfx", None)
    return out


def verify_pools(ops, d=None):
    """Problems for any sound-link op outside its row's pool. Music keys take whole looping tracks (or silence), fanfare
    and jingle keys take fanfares and jingles, song playbacks take songs and ocarina notes take the flute's. An OoTR
    sound setting has to pick a sound of the same kind (loop or one-shot) that every user sharing the key loads itself.
    A remake_shuffle_all_sfx swap stays within one archive and kind."""
    d = d or json.load(open(SOUND, encoding="utf-8"))
    pools = _pools(d)
    sfx_rows = {(r["user"], r["key"], r["was"]): r for rows in d["sfx"].values() for r in rows}
    bars = {b: {e["sound"]: e for e in es} for b, es in d["sfx_bars"].items()}
    kind_of = {n: (a, k) for a, kinds in d.get("sfx_all", {}).items() for k, ns in kinds.items() for n in ns}
    problems = []
    for op in ops:
        if "remap" in op:
            for a, b in sorted(op["remap"].items()):
                if a not in kind_of or kind_of.get(a) != kind_of.get(b):
                    problems.append(f"sound: all-sfx swap {a} -> {b} crosses an archive or kind "
                                    f"({kind_of.get(a)} / {kind_of.get(b)})")
            continue
        row = (op["user"], op["key"], op["was"])
        if row not in pools:
            problems.append(f"sound: {op['user']}/{op['key']} ({op['was']} -> {op['asset']}) is no row of any pool")
            continue
        name, allowed = pools[row]
        if allowed is not None:
            if op["asset"] not in allowed:
                problems.append(f"sound: {name} key {op['user']}/{op['key']} ({op['was']}) plays {op['asset']}, "
                                f"which isn't in its pool")
            continue
        if op["asset"] == S.BLANK:
            continue
        r = sfx_rows[row]
        for u in r["aliases"]:
            e = next((bars[b][op["asset"]] for b in d["sfx_users"].get(u, []) if op["asset"] in bars.get(b, {})), None)
            if e is None:
                problems.append(f"sound: {op['user']}/{op['key']} plays {op['asset']}, not in {u}'s own sound files")
            elif bool(e["loop"]) != bool(r.get("loop")):
                problems.append(f"sound: {op['user']}/{op['key']} ({op['was']}, "
                                f"{'a loop' if r.get('loop') else 'one-shot'}) plays {op['asset']}, "
                                f"{'a loop' if e['loop'] else 'one-shot'}")
    return problems


def verify(romfs, patch_dir, plan):
    """Problems with a built patch's sounds beyond its bytes. Checks the music graph (_cosmetics_bgm.verify: whole
    tracks play whole from their start, slots get the right kind of track, no fork plays a track twice) and every op's
    pool."""
    cos = plan.get("cosmetics") or {}
    if not cos.get("slink"):
        return []
    fs = Romfs(romfs, VANILLA)
    p = os.path.join(patch_dir, S.SLINK)
    if not os.path.exists(p):
        return [f"sound: {S.SLINK} is missing from the patch"]
    new = fs.zs.decompress(open(p, "rb").read())
    return B.verify(fs, patch_dir, new, (cos.get("log") or {}).get("music_check")) + verify_pools(cos["slink"])


def _bytes_differ(a, b):
    """How many of the first min(len(a), len(b)) bytes differ, so sum(x != y for x, y in zip(a, b)), counted with numpy.
    A seed's sound files are ~300 MB and the plain Python count took ~25 s of the app's cosmetics check."""
    import numpy as np
    n = min(len(a), len(b))
    return int(np.count_nonzero(np.frombuffer(a, np.uint8, n) != np.frombuffer(b, np.uint8, n)))


def main(romfs, patch_dir, *plans):
    check = "--check" in plans
    plans = [p for p in plans if p != "--check"]
    cos = load(plans)
    fs, files = build(romfs, cos)
    for rel, new in sorted(files.items()):
        dst = os.path.join(patch_dir, rel)
        raw = fs.raw(rel)
        old = fs.zs.decompress(raw)
        if len(new) != len(old):
            # only the map icons grow files (the UI's two archives), and only make_patch raises a grown file's
            # size-table entry: here they must already be in the patch as make_patch wrote them
            if not cos.get("map_icons"):
                sys.exit(f"cosmetics: {rel} changed size ({len(old)} -> {len(new)}); edits must be in place")
            if not check:
                if not os.path.exists(dst) or fs.zs.decompress(open(dst, "rb").read()) != new:
                    sys.exit(f"cosmetics: {rel} grows ({len(old)} -> {len(new)}): build the patch with make_patch, "
                             f"which raises its size-table entry")
                print(f"  ok {rel}: as make_patch wrote it ({len(new) - len(old)} bytes more than vanilla)")
                continue
        if check:
            if not os.path.exists(dst):
                sys.exit(f"cosmetics check: {rel} is missing from {patch_dir}")
            got = fs.zs.decompress(open(dst, "rb").read())
            if got != new:
                sys.exit(f"cosmetics check: {rel} in {patch_dir} differs from the plan")
            print(f"  ok {rel}: {_bytes_differ(old, got)} bytes differ from vanilla")
            continue
        if new == old:
            continue
        fs.snapshot(rel)  # tools/install.py needs the vanilla copy, as for every file make_patch writes
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        open(dst, "wb").write(fs.zs.compress(new, fs.zs.dict_id(raw)))
        print(f"  wrote {rel} ({_bytes_differ(old, new)} bytes changed)")
    n_sl = len(cos["slink"])
    print(f"cosmetics: {n_sl} sound-link edits, {len(cos['textures'])} texture recolours, "
          f"{len(cos['effects'])} effect colour groups, {len(cos['hud'])} HUD edits, "
          f"{len(files)} files {'checked' if check else 'written'}")
    if check:
        problems = []
        for p in plans:
            problems += verify(romfs, patch_dir, json.load(open(p, encoding="utf-8")))
        for x in problems:
            print("  " + x)
        if problems:
            sys.exit(f"cosmetics check: {len(problems)} problems")
        print("  sounds read back: music graph and pools ok")


if __name__ == "__main__":
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    try:
        main(*sys.argv[1:])
    except ValueError as e:
        sys.exit(f"cosmetics error: {e}")
