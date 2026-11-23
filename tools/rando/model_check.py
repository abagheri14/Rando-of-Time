"""Read-back: every model the patch makes an actor show can be loaded.

If a model's name dictionary is wrong, the item shows nothing on the ground and the hold-up crashes (an empty
ShowItem slot). With test_guardroom3 that happened to Pot 40's Zelda's Lullaby and Pot 35's Master Sword, even
though their packs, ModelInfo, model files and size entries were all in place. A renamed copy kept the donor's
dictionary tree, so the game's lookup of the model by its FmdbName missed (tools/rando/res_dict.py). No other
read-back looks inside the model files.

verify(patch, romfs) -> (problems, models checked):
- every ModelInfo the patch adds or changes (Component/ModelInfo/*.bgyml in a patched Pack/Actor pack, and the model
  fields of every ActorInfo row it adds or changes) names a model file that exists (Model/<ModelProjectName>.
  <FmdbName>.bfres.zs, in the patch or the game) and whose model dictionary finds FmdbName;
- every model or texture file the patch writes (Model/*.bfres.zs, Tex/*.bntx.zs): its size-table entry holds it
  (a file bigger than its entry doesn't load), and every name dictionary in it finds all its keys;
- every texture a model the patch writes names loads (in the patch or the game), unless the game's own models of
  that project name it without the file too (_texture_problems).
Vanilla files and unchanged ModelInfo are the game's own and not re-read."""
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(HERE, "tools"))
sys.path.insert(0, os.path.join(HERE, "tools", "rando"))
import res_dict  # noqa: E402

RSTB = "System/Resource/ResourceSizeTable.Product.111.Nin_Ounce_NVN2.rsizetable.zs"
ACTOR_INFO = "RSDB/ActorInfo.Product.111.rstbl.byml.zs"
MODEL_DICT = 0x30  # BFRES header: the model dictionary's offset


def _model_rel(project, fmdb):
    return f"Model/{project}.{fmdb}.bfres.zs"


def _installed_new(original):
    """Files tools/install.py added to the game folder (installed.json "new_files", as make_patch reads it). With a
    test installed they sit in the romfs, but they aren't the game's own."""
    import json
    record = os.path.join(os.path.dirname(os.path.abspath(original)), "installed.json")
    if not os.path.exists(record):
        return set()
    return {os.path.normpath(r) for r in (json.load(open(record, encoding="utf-8")).get("new_files") or {})}


def verify(patch, romfs):
    from romtools import Romfs, Restbl, byml_load, sarc_files
    original = os.environ.get("REMAKE_ORIGINAL") or os.path.join(HERE, "original")
    fs = Romfs(romfs, original, [patch])
    van = Romfs(romfs, original)
    ours = _installed_new(original)
    bad, named = [], {}  # named: model file -> (FmdbName, who names it)

    def in_game(rel):  # exclude files added by an installed test
        return os.path.exists(os.path.join(romfs, rel)) and os.path.normpath(rel) not in ours

    def exists(rel):
        return os.path.exists(os.path.join(patch, rel)) or in_game(rel)

    pack_dir = os.path.join(patch, "Pack", "Actor")
    for name in sorted(os.listdir(pack_dir)) if os.path.isdir(pack_dir) else []:
        if not name.endswith(".pack.zs"):
            continue
        rel = f"Pack/Actor/{name}"
        files = sarc_files(fs.read(rel))
        old = sarc_files(van.read(rel)) if in_game(rel) else {}
        for inner, data in files.items():
            if not inner.startswith("Component/ModelInfo/") or old.get(inner) == data:
                continue
            mi = byml_load(data)[0]
            project, fmdb = mi.get("ModelProjectName"), mi.get("FmdbName")
            if not project or not fmdb:
                continue  # Some vanilla entries have no model here. Others inherit it from $parent.
            named.setdefault(_model_rel(project, fmdb), (fmdb, f"{rel}:{inner}"))
    if os.path.exists(os.path.join(patch, ACTOR_INFO)):
        old_rows = {r["__RowId"]: r for r in byml_load(van.read(ACTOR_INFO))[0]}
        for r in byml_load(fs.read(ACTOR_INFO))[0]:
            o = old_rows.get(r["__RowId"]) or {}
            if r.get("ModelProjectName") and r.get("FmdbName") and \
                    (o.get("ModelProjectName"), o.get("FmdbName")) != (r["ModelProjectName"], r["FmdbName"]):
                named.setdefault(_model_rel(r["ModelProjectName"], r["FmdbName"]),
                                 (r["FmdbName"], f"ActorInfo row {r['__RowId']}"))
    for rel, (fmdb, who) in sorted(named.items()):
        if not exists(rel):
            bad.append(f"{who} names {rel}, which is in neither the patch nor the game")
            continue
        data = fs.read(rel)
        if len(data) < MODEL_DICT + 8 or not res_dict.has(data, fmdb, int.from_bytes(data[MODEL_DICT:MODEL_DICT + 8],
                                                                                        "little")):
            bad.append(f"{who} names {rel}: its model dictionary doesn't find {fmdb} (the game can't load it by name)")
    rstb = Restbl(fs.zs.decompress(fs.raw(RSTB)))
    written = 0
    for sub, ext in (("Model", ".bfres.zs"), ("Tex", ".bntx.zs")):
        d = os.path.join(patch, sub)
        for name in sorted(os.listdir(d)) if os.path.isdir(d) else []:
            if not name.endswith(ext):
                continue
            rel = f"{sub}/{name}"
            data = fs.read(rel)
            written += 1
            entry = rstb.get(rel[:-3])
            if entry is None or entry < len(data):
                bad.append(f"{rel}: {len(data)} bytes, its size-table entry {entry}: it wouldn't load")
            bad += res_dict.problems(data, rel)
            if sub == "Model" and data[:4] == b"FRES":
                bad += _texture_problems(rel, data, patch, romfs, van, in_game)
    return bad, len(named) + written


def _texture_problems(rel, data, patch, romfs, van, in_game):
    """For a model the patch writes, every texture its materials name loads (Tex/<name>.bntx.zs in the patch or the
    game), or is missing for the game's own models of its project too (a slot the game leaves empty). Otherwise the
    model would lose that texture in game. The soul figures, for example, name reduced copies of the boss's
    textures."""
    from parity import _appearance_bfres as ab
    try:
        mats = ab.materials(data)
    except (ValueError, IndexError):
        return [f"{rel}: its materials can't be read"]
    project = os.path.basename(rel).split(".")[0]
    vanilla_names = None
    out = []
    for t in sorted({t for m in mats for t in m["textures"]}):
        tex = f"Tex/{t}.bntx.zs"
        if os.path.exists(os.path.join(patch, tex)) or in_game(tex):
            continue
        if vanilla_names is None:  # the textures the game's own models of this project name
            vanilla_names = set()
            mdir = os.path.join(romfs, "Model")
            for name in os.listdir(mdir):
                if name.startswith(project + ".") and name.endswith(".bfres.zs") and in_game(f"Model/{name}"):
                    try:
                        vanilla_names |= {x for m in ab.materials(van.read(f"Model/{name}")) for x in m["textures"]}
                    except (ValueError, IndexError):
                        pass
        if t not in vanilla_names:
            out.append(f"{rel}: names texture {t}, which neither the patch nor the game has (it would lose that "
                       f"texture)")
    return out


if __name__ == "__main__":
    problems, n = verify(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else __import__("romtools").longshot_romfs())
    for x in problems:
        print(x)
    print(f"{len(problems)} problems; {n} models and textures read back")
