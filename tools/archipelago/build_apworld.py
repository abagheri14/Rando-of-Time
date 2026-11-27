"""Build rando_of_time.apworld (Archipelago's custom_worlds) from apworld/rando_of_time.

  python tools/archipelago/build_apworld.py [OUT.apworld]       (default: apworld/dist/rando_of_time.apworld)

The zip holds the world's source (apworld/rando_of_time/*.py) plus files made here:
- ids.json: data/archipelago/ids.json (Archipelago needs every id when it imports the world)
- options.json: the options, from release/data/settings_schema.json (gameplay tabs; cosmetics and sounds go
  through extra_settings)
- archipelago.json: the apworld manifest
- LICENSE-OotrR.txt: OotrR's MIT notice (the structure of this world is ported from its apworld).
Our generator isn't in it. The world runs the randomizer folder set in host.yaml (see the world's docstring).
"""
import json
import os
import re
import sys
import zipfile

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(HERE, "apworld", "rando_of_time")
PACKAGE = "rando_of_time"
WORLD_VERSION = "0.9.0"
MINIMUM_AP_VERSION = "0.6.2"
SKIP_TABS = ("cosmetics_tab", "sfx_tab")
# Archipelago's own per-game options: never shadowed by ours
AP_COMMON = {"accessibility", "progression_balancing", "local_items", "non_local_items", "start_inventory",
             "start_hints", "start_location_hints", "exclude_locations", "priority_locations", "item_links",
             "plando_items", "start_inventory_from_pool", "death_link", "extra_settings"}
OOTRR_NOTICE = """Parts of this apworld are ported from OotrR's apworld (https://github.com/Mozencaz/OotrR):
the one-region world with a cached-sweep access rule, the option classes made from a list, the patch-per-player output.

MIT License

Copyright (c) 2026 Mozencaz

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""


def ap_name(value, taken):
    """A choice value as an Archipelago option name (option_<name>): "random" is Archipelago's own roll."""
    name = re.sub(r"[^0-9a-z_]", "_", str(value).lower()) or "value"
    if name == "random":
        name = "randomized"
    base, n = name, 2
    while name in taken:
        name, n = f"{base}_{n}", n + 1
    taken.add(name)
    return name


def effective_defaults():
    """What a seed uses when a setting isn't given. That's config/rando_settings.json (as generate.load_settings reads
    it), else OoT Randomizer's own default.
    The schema's "default" is OoTR's GUI default, and that's different for some settings (bridge, the dungeon items,
    the Door of Time...). The options have to start from what the randomizer really uses, so an empty YAML is the app's
    default seed and a value equal to the default means the same thing."""
    import contextlib
    import io
    for p in (os.path.join(HERE, "tools"), os.path.join(HERE, "tools", "rando")):
        if p not in sys.path:
            sys.path.insert(0, p)
    with contextlib.redirect_stdout(io.StringIO()):
        import generate
        base = generate.load_settings(os.path.join(HERE, "config", "rando_settings.json"))
        from SettingsList import SettingInfos
    out = dict(base)
    for name, info in SettingInfos.setting_infos.items():
        if name not in out and getattr(info, "default", None) is not None:
            out[name] = info.default
    return out


def option_specs(schema_path=None):
    schema = json.load(open(schema_path or os.path.join(HERE, "release", "data", "settings_schema.json"),
                            encoding="utf-8"))
    eff = effective_defaults()
    out = []
    for tab in schema["tabs"]:
        if tab["name"] in SKIP_TABS:
            continue
        for section in tab["sections"]:
            for x in section["settings"]:
                name, kind = x["name"], x["type"]
                if name in AP_COMMON or "default" not in x:
                    continue
                x = dict(x, default=eff.get(name, x["default"]))
                spec = {"name": name, "label": x.get("label") or name, "help": x.get("tooltip") or "",
                        "our_default": x["default"]}
                if kind == "bool":
                    spec.update(kind="bool", default=bool(x["default"]))
                elif kind == "choice":
                    taken = set()
                    values = [[ap_name(c[0], taken), c[0]] for c in x["choices"]]
                    ours = [v for _a, v in values]
                    if x["default"] not in ours:
                        print(f"note: {name}: default {x['default']!r} is not one of its choices: extra_settings only")
                        continue
                    spec.update(kind="choice", values=values, default_index=ours.index(x["default"]))
                elif kind == "int" and "min" in x and "max" in x:
                    spec.update(kind="range", min=int(x["min"]), max=int(x["max"]),
                                default=min(max(int(x["default"]), int(x["min"])), int(x["max"])))
                elif kind == "list" and x.get("choices"):
                    spec.update(kind="set", keys=[str(c[0]) for c in x["choices"]],
                                default=[str(v) for v in x["default"]])
                elif kind == "list":
                    spec.update(kind="list", default=list(x["default"]))
                elif kind == "dict":
                    spec.update(kind="dict", default=x["default"])
                else:  # an int without bounds: extra_settings
                    continue
                out.append(spec)
    return out


def manifest():
    return {"game": "Rando of Time", "world_version": WORLD_VERSION, "minimum_ap_version": MINIMUM_AP_VERSION,
            "authors": ["Rando of Time"], "version": 7, "compatible_version": 7}


def build(out=None):
    out = out or os.path.join(HERE, "apworld", "dist", f"{PACKAGE}.apworld")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    ids = os.path.join(HERE, "data", "archipelago", "ids.json")
    specs = option_specs()
    tmp = out + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for name in sorted(os.listdir(SRC)):
            if name.endswith(".py"):
                z.write(os.path.join(SRC, name), f"{PACKAGE}/{name}")
        z.write(ids, f"{PACKAGE}/ids.json")
        z.writestr(f"{PACKAGE}/options.json", json.dumps({"options": specs}, ensure_ascii=False, indent=0))
        z.writestr(f"{PACKAGE}/archipelago.json", json.dumps(manifest(), indent=1))
        z.writestr(f"{PACKAGE}/LICENSE-OotrR.txt", OOTRR_NOTICE)
    os.replace(tmp, out)
    print(f"{out}: {len(specs)} options")
    return out


def write_source_data():
    """The same generated files next to the source, for the test harness (it imports the folder, not the zip)."""
    import shutil
    shutil.copyfile(os.path.join(HERE, "data", "archipelago", "ids.json"), os.path.join(SRC, "ids.json"))
    with open(os.path.join(SRC, "options.json"), "w", encoding="utf-8") as f:
        json.dump({"options": option_specs()}, f, ensure_ascii=False, indent=0)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    write_source_data()
    build(args[0] if args else None)
