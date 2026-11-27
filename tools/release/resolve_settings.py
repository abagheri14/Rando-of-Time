"""Prints a settings file as JSON, the way the generator reads it. The randomizer app loads settings files with this.

  python tools/release/resolve_settings.py FILE

Follows the file's "base" chain (config/rando_settings.json included) and maps familiar names (config/
setting_aliases.json, e.g. shuffle_trees) to the remake's own keys, exactly as tools/rando/generate.py does.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(HERE, "tools", "rando"))


def split_tables(d):
    """Splits table settings back into the entries the app shows one at a time, whether the table is given whole or by
    entry. These are config/setting_aliases.json entries with an "item", e.g. remake_trap_weights shown as
    remake_trap_weight_<kind>."""
    table = json.load(open(os.path.join(HERE, "config", "setting_aliases.json"), encoding="utf-8"))["names"]
    parts = {}
    for name, a in table.items():
        if "item" in a:
            parts.setdefault(a["key"], []).append((name, a))
    for key, entries in parts.items():
        if not isinstance(d.get(key), dict):
            continue
        whole = d.pop(key)
        for name, a in entries:
            d[name] = whole.get(a["item"], 0)  # an entry the table leaves out weighs nothing
    gk = d.get("remake_gk_durability")
    if isinstance(gk, int) and not isinstance(gk, bool):  # older form, the number of hits is the setting itself
        d["remake_gk_durability"], d["remake_gk_durability_hits"] = "fixed", gk
    return d


def main(path):
    import generate
    import glitch_ui  # the remake glitch tricks become the app's own switches
    try:
        d = glitch_ui.split(split_tables(generate.load_settings(os.path.abspath(path))))
    except Exception as e:  # noqa: BLE001 - shown to the player as is
        print(json.dumps({"error": str(e)}))
        return 1
    print(json.dumps({"settings": d}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
