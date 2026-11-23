"""Archipelago options for Rando of Time. They're our own settings under their own names, so a player's YAML reads
like the randomizer's settings file. options.json lists them with their values and defaults, and
tools/archipelago/build_apworld.py writes it from the randomizer's release/data/settings_schema.json. The gameplay
tabs become options, and anything else (cosmetics, sounds, settings the schema doesn't show) goes in
`extra_settings`.

Only values that differ from the schema's default reach the generator. The rest come from the randomizer's own
config/rando_settings.json, same as in the app. The structure (option classes made from a list, a dataclass of
them) follows OotrR's apworld (github.com/Mozencaz/OotrR, MIT License, Copyright (c) 2026 Mozencaz).
"""
import json
import pkgutil
from dataclasses import make_dataclass

from Options import (Choice, DefaultOnToggle, OptionDict, OptionList, OptionSet, PerGameCommonOptions, Range,
                     StartInventoryPool, Toggle)

SPECS = json.loads(pkgutil.get_data(__name__.rsplit(".", 1)[0], "options.json").decode("utf-8"))["options"]


def _option_class(spec):
    name = "".join(part.title() for part in spec["name"].split("_"))
    attrs = {"__doc__": spec.get("help") or spec["label"], "display_name": spec["label"], "__module__": __name__}
    kind = spec["kind"]
    if kind == "bool":
        return type(name, (DefaultOnToggle if spec["default"] else Toggle,), attrs)
    if kind == "choice":
        for index, (ap_name, _value) in enumerate(spec["values"]):
            attrs["option_" + ap_name] = index
        attrs["default"] = spec["default_index"]
        return type(name, (Choice,), attrs)
    if kind == "range":
        attrs.update(range_start=spec["min"], range_end=spec["max"], default=spec["default"])
        return type(name, (Range,), attrs)
    if kind == "set":
        attrs.update(valid_keys=frozenset(spec["keys"]), default=frozenset(spec["default"]))
        return type(name, (OptionSet,), attrs)
    if kind == "list":
        attrs["default"] = list(spec["default"])
        return type(name, (OptionList,), attrs)
    attrs["default"] = dict(spec["default"])
    return type(name, (OptionDict,), attrs)


class ExtraSettings(OptionDict):
    """Any other Rando of Time setting by its own name (cosmetics, sounds, plando...), applied over the options
    above. Example: {"default_targeting": "hold", "kokiri_color": "Kokiri Green"}."""
    display_name = "Extra settings"
    default = {}


OPTION_CLASSES = {spec["name"]: _option_class(spec) for spec in SPECS}
for _cls in OPTION_CLASSES.values():
    globals()[_cls.__name__] = _cls

RandoOfTimeOptions = make_dataclass(
    "RandoOfTimeOptions",
    [(name, cls) for name, cls in OPTION_CLASSES.items()]
    + [("extra_settings", ExtraSettings), ("start_inventory_from_pool", StartInventoryPool)],
    bases=(PerGameCommonOptions,))
RandoOfTimeOptions.__module__ = __name__


def our_settings(options):
    """The options as our settings dict: only values that differ from the schema's default, plus extra_settings."""
    out = {}
    for spec in SPECS:
        option = getattr(options, spec["name"])
        kind = spec["kind"]
        if kind == "bool":
            value = bool(option.value)
        elif kind == "choice":
            value = spec["values"][option.value][1]
        elif kind == "range":
            value = int(option.value)
        elif kind == "set":
            value = [k for k in spec["keys"] if k in option.value]
        elif kind == "list":
            value = list(option.value)
        else:
            value = dict(option.value)
        default = spec["our_default"]
        if (sorted(value) != sorted(default) if kind == "set" else value != default):
            out[spec["name"]] = value
    out.update(dict(options.extra_settings.value))
    return out
