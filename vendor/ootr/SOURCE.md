# Vendored: OoT Randomizer generator

- Project: OoT Randomizer, https://github.com/OoTRandomizer/OoT-Randomizer
- Commit: `526b4c8d81b7c4023ef4573ffbaf39344e270d5b` (branch `Dev`, committed 2026-11-02), the same commit as
  `reference/ootr/`.
- Fetched 2026-11-18 from `https://raw.githubusercontent.com/OoTRandomizer/OoT-Randomizer/<commit>/<path>`; every file
  checked against its git blob hash from the GitHub tree API.
- Files: the 63 Python modules at the repo root, `LICENSE`, `requirements.txt`, and from `data/`: `World/`, `Hints/`,
  `Presets/`, `Bingo/`, `lang/English/property.json`, `LogicHelpers.json`, `presets_default.json`, `settings_mapping.json` (117 files, 3.95 MB). `data/generated/` is created empty; OoTR writes its own caches there.
  Not fetched: glitch logic, voices, language packs, textures, generated ROM symbols and other N64 patching data.

## License

`LICENSE`: "All files are MIT licensed unless stated otherwise." The only other license files in the repo at this
commit are under `bin/` and `Notes/Chest Textures/rgba5551topng/`; nothing was taken from those. Keep `LICENSE` with
these files and with anything derived from them.

## How we use it

Only OoTR's seed generation (world model, logic search, item pools, fill, hints, spoiler) runs, through
`tools/rando/`. Its N64 ROM patching (`Patches.py`, `Rom.py` and friends) is never called; the remake is patched by
`tools/make_patch.py`. Files here are kept unmodified so they can be compared with upstream; remake differences live
in the adapter.
