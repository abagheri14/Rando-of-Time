"""Trick and glitch switches for the remake logic.

Everything is off unless config/tricks.json -> "enabled" names it. Logic code always gets trick
values through `trick_values()` and never defaults a trick to on.

usage: python tools/logic_settings.py        (prints what is enabled and checks the names)
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(HERE, "config", "tricks.json")
LOGIC = os.path.join(HERE, "reference", "ootr", "logic.json")


def known_tricks():
    return set(json.load(open(LOGIC, encoding="utf-8"))["tricks"])


def enabled_tricks():
    names = json.load(open(CONFIG, encoding="utf-8")).get("enabled", [])
    unknown = sorted(set(names) - known_tricks())
    if unknown:
        raise ValueError(f"config/tricks.json names tricks that do not exist: {unknown}")
    return set(names)


def trick_values():
    """{trick name: bool} for every known trick or glitch, True only for the ones listed as enabled."""
    on = enabled_tricks()
    return {t: t in on for t in sorted(known_tricks())}


if __name__ == "__main__":
    values = trick_values()
    on = [t for t, v in values.items() if v]
    print(f"{len(values)} tricks/glitches known; enabled: {', '.join(on) if on else 'none'}")
    sys.exit(0)
