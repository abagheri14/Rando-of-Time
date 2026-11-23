"""Read-back for the OoTR gameplay settings we closed.

Every feature leaves a note under the plan's "_gaps" section ({feature: note}). verify() reads the built patch back
for each note and returns the problems, and tools/rando/in_game_check.py prints them. A note no reader knows is a
problem too, so a feature can't skip its read-back."""


# feature -> (module in tools/rando/parity, its read-back function(patch, note, romfs) -> [problem])
READERS = {
    "ganon_bosskey": ("_dungeons_ganon", "verify"),
    "zora_fountain_fast": ("_gaps_story", "verify_zora_fast"),
    "drops": ("_gaps_drops", "verify"),
    "tcg_keys": ("_chests_tcg", "verify_keyed"),
    "dampe_fix": ("_chests_dampe", "verify_fix"),
    "silver_rupees": ("_dungeons_silver_shuffle", "verify"),
    "triforce_look": ("_gaps_triforce_look", "verify"),  # the Triforce pieces' model and display (dungeons)
    "small_keys": ("_dungeons_keys", "verify"),  # every small-key credit writes the game's three key rows (dungeons)
    "dungeon_items": ("_dungeons_routes", "verify"),  # every placed dungeon item's give path reaches its credit
    "dungeon_text": ("_dungeons_text", "verify"),  # every dungeon item's window names its dungeon, every language
    "starting_hearts": ("_start_hearts", "verify"),  # Life/MaxLife and, below 3, the containers added
    "show_models": ("_show_models", "verify_note"),  # the Ocarina buttons' labelled models (songs_trade.finish_plan)
    "shop_deals": ("_shops_deals", "verify"),  # special deals sold by their own steps (shops)
    "shop_shelves": ("_shops_deals", "verify_shelves"),  # every changed shelf: price, pick, count board, placement
}


def _readers():
    """READERS plus the READERS of each story gaps module (parity/story.py GAPS_MODULES)."""
    from parity import story
    out = dict(READERS)
    for m in story.gaps_modules():
        for key, fn in getattr(m, "READERS", {}).items():
            out[key] = (m.__name__.split(".")[-1], fn)
    return out


def verify(patch, gaps, romfs):
    import importlib
    readers = _readers()
    bad = []
    for key, note in sorted((gaps or {}).items()):
        if key not in readers:
            bad.append(f"_gaps: no read-back for {key}")
            continue
        mod, fn = readers[key]
        bad += [f"{key}: {x}" for x in getattr(importlib.import_module(f"parity.{mod}"), fn)(patch, note, romfs)]
    return bad
