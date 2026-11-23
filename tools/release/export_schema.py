"""The settings the randomizer app shows (release/app reads release/data/settings_schema.json).

  python tools/release/export_schema.py [OUT]     default: release/data/settings_schema.json

We only offer what the remake can make. That's OoTR's settings in OoTR's own tabs and sections
(vendor/ootr/data/settings_mapping.json, its labels and tooltips), each with the values the patcher accepts
(world_settings APPLIED / SUPPORTED, the plugins' OWNS, GENERATOR_ANY = any value). Settings pinned to the
remake's behaviour (REMAKE_ONLY) or not handled yet are left out, so a seed can't fail on them. The remake's own
settings (the plugins' REMAKE_SETTINGS) show in OoTR's tabs and sections too, each next to the OoTR setting that
OoTR or Ship of Harkinian lists it with (tools/release/remake_ui.py has where, label and explanation). The few
with no such home go at the end of OoTR's "Other" tab.
"""
import importlib
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(HERE, "tools", "rando"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import remake_ui  # noqa: E402
OUT = os.path.join(HERE, "release", "data", "settings_schema.json")
SKIP_TABS = {"general_tab", "general_tab_web_patcher"}  # ROM paths and output types are the app's job
EXCLUDE = {"randomize_settings"}  # OoTR's "randomize main rules" picks any value, also ones the remake can't make
# typos in OoTR's own tooltips, fixed in what the app shows (shuffle_gerudo_valley_river_exit: "where the the")
TOOLTIP_TYPOS = {"Randomize where the the ": "Randomize where the "}
# OoTR tooltips that describe the original game's spots, which the remake doesn't have, reworded for the remake.
# shuffle_beehives: OoTR has 32 hives in many grottos. The remake has 7, with a set for each age (drop_map
# "beehive", 14 locations), and all of them need can_break_upper_beehive: Boomerang, Hookshot, Bow, Din's Fire
# (drops.REMAKE_HELPERS). The Slingshot does no damage (SlingshotBullet rate 0).
REMAKE_TIPS = {"shuffle_beehives": "Enabling this will let beehives drop items. The remake has 7 beehives, all in the "
                                   "grotto under the lid next to Kakariko's House of Skulltula, and child and adult each "
                                   "find their own 7: 14 in all. The logic counts every way the remake breaks them: the "
                                   "Boomerang, the Hookshot, the Bow and Din's Fire. The Slingshot can't, unless "
                                   "Slingshot Breaks Beehives is on.",
              # OoTR's "9 cows, and an extra in MQ Jabu": data/rando/songs_trade_cows.json not_in_remake / remake_only.
              # The remake's own Gerudo Fortress cow is the location GF Cow.
              "shuffle_cows": "Enabling this will let cows give you items upon performing Epona's song in front of them. "
                              "The remake has 8 cows: 7 of the original's (Link's house, the Hyrule Field and Death "
                              "Mountain Trail cow grottos, the two Lon Lon Ranch stable cows, Impa's house and Gerudo "
                              "Valley) and its own new cow in Gerudo's Fortress, by the horseback archery stable (adult; "
                              "the guard on the way there wants the Gerudo Membership Card). The two in the Lon Lon "
                              "Ranch tower aren't in the remake.",
              # OoTR's wonder item kinds, see parity/drops.py. The remake has no invisible item actor, so there's
              # nothing to shuffle.
              "shuffle_wonderitems": "In the original game, wonder items are invisible items that drop something when "
                                     "Link touches a spot or hits it (OoTR's Shuffle Wonderitems). The remake doesn't "
                                     "use them, so this setting has nothing to shuffle and changes nothing."}
# OoTR settings where the remake allows a wider range than OoTR does, with our own text. starting_hearts goes 1-20.
# OoTR stops at 3, but Ship of Harkinian and the 3DS randomizer go down to 1 (world_settings.LOW_HEARTS).
WIDER = {"starting_hearts": ((1, 20), "Start the game with the selected number of hearts. Above 3, Heart Containers "
                                      "and Pieces of Heart are removed from the item pool in equal proportion. Below 3, "
                                      "Heart Containers are added to the item pool in place of junk, so you can still "
                                      "reach 20 hearts.")}
NO_PROBE = {"disabled_locations"}
# Settings files use these but OoTR's GUI never shows them (its tabs split them up), so they go in a tab's last section
EXTRA_IN_TAB = {"starting_tab": ["starting_items"], "other_tab": ["password_lock"]}  # (OoTR: its general tab)
# OoTR settings where our default (config/rando_settings.json) isn't OoTR's, with our own text
REMAKE_DEFAULTS = {
    "auto_equip_masks": (True, "The remake already keeps a worn mask on through area changes and reloads (time "
                               "travel takes it off), so this is on by default. Turn it off to bring back the original "
                               "game's behaviour: a mask comes off at every loading zone and after loading a save."),
    "fast_chests": (False, "Big chests open as quickly as small ones: Link lifts the lid and holds the item up right "
                           "away, instead of the big chest's long cutscene. Small chests are already quick in the "
                           "remake."),
}
EXTRA_LABELS = {"starting_items": ("Other starting items", 'Item names and counts, as OoTR writes them in a settings '
                                   'file, e.g. {"Bottle": 1, "Piece of Heart": 4}. Adds to the lists above.')}  # 2,000+ spots, any of them can be left out


def _plain(v):
    if isinstance(v, (list, tuple, set)):
        return [_plain(x) for x in v]
    if isinstance(v, dict):
        return {str(k): _plain(x) for k, x in v.items()}
    return v


def _disable_rules(info):
    """OoTR's GUI dependencies as [{"when": value or "!value", "settings": [...]}].
    A setting is greyed out while its parent has that value, and "!v" means any value but v. Sections and tabs it turns
    off count as their settings."""
    from SettingsList import get_settings_from_section, get_settings_from_tab
    out = []
    for when, what in (getattr(info, "disable", None) or {}).items():
        names = list(what.get("settings", []))
        names += [n for sec in what.get("sections", []) for n in get_settings_from_section(sec)]
        names += [n for tab in what.get("tabs", []) for n in get_settings_from_tab(tab)]
        if names:
            out.append({"when": str(when), "settings": names})
    return out


def _enablers(infos):
    """{dependent: (parent, value)}, the parent value that turns a dependent setting on. That's the v of a '!v' rule, or
    for rules that name the values that disable it, the first other value."""
    out = {}
    for parent, info in infos.items():  # first the "only with this value" rules, since they name the value
        for when, what in (getattr(info, "disable", None) or {}).items():
            for dep in what.get("settings", []):
                if isinstance(when, str) and when.startswith("!"):
                    out.setdefault(dep, (parent, when[1:]))
    for parent, info in infos.items():
        rules = getattr(info, "disable", None) or {}
        off = {}
        for when, what in rules.items():
            if not (isinstance(when, str) and when.startswith("!")):
                for dep in what.get("settings", []):
                    off.setdefault(dep, set()).add(when)
        for dep, vals in off.items():
            on = [v for v in (getattr(info, "choices", None) or {True: 1, False: 0}) if v not in vals]
            if on and dep not in out:
                out[dep] = (parent, on[0])
    return out


class Prober:
    """Which values the remake can make. Each value is tried on top of the default settings, with whatever parent value
    turns it on, and kept if it adds no problem (generate.settings_problems)."""

    def __init__(self, generate):
        self.g = generate
        Main, _, _, _, self.Settings, _ = generate.ootr()
        self.Main = Main
        self.mods = generate.plugins()
        self.base = generate.load_settings(os.path.join(HERE, "config", "rando_settings.json"))
        self.base_problems = set(self.problems({}))

    def problems(self, over):
        import contextlib
        import io
        cfg = dict(self.base, **over)
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                s = self.g.make_settings(self.Settings, cfg, 1, [], None)
                self.Main.resolve_settings(s)
                return self.g.settings_problems(s, self.mods)
        except Exception as e:  # noqa: BLE001 - OoTR's validation raises plain errors
            return [f"invalid: {e}"]

    def ok(self, over):
        return not (set(self.problems(over)) - self.base_problems)


def _enemy_choices():
    """[actor name, plain name] of every enemy type the enemizer can swap (data/rando/enemizer.json)."""
    import re
    types = json.load(open(os.path.join(HERE, "data", "rando", "enemizer.json"), encoding="utf-8"))["types"]

    def plain(name):
        words = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name.replace("Enemy_", "")).replace("_", " ")
        return words[:1].upper() + words[1:]
    return [[n, plain(n)] for n in sorted(types, key=plain)]


def _trap_kinds():
    from parity import chests
    return list(chests.TRAP_KINDS)


def _place(tabs, placed, mapping):
    """Puts the remake's settings into OoTR's tabs. Each (anchor, entry) goes right after its anchor setting, several
    after one anchor in remake_ui's order. If the export doesn't show the anchor, it goes at the end of the anchor's
    OoTR section, and an anchor written as "tab/section" means the end of that section. If the export has nothing in a
    section yet we make it, with OoTR's name for its sections and remake_ui.SECTION_TEXT for the remake-only one."""
    home, ootr_order = {}, {}
    for t in mapping["Tabs"]:
        for i, sec in enumerate(t.get("sections", [])):
            ootr_order[(t["name"], sec["name"])] = i
            for n in sec.get("settings", []):
                home.setdefault(n, (t["name"], sec["name"]))
    shown = {e["name"] for t in tabs for s in t["sections"] for e in s["settings"]}
    ours = {e["name"] for _, e in placed}
    after, ends = {}, {}
    for anchor, e in placed:
        if anchor in shown or anchor in ours:
            after.setdefault(anchor, []).append(e)
        elif "/" in anchor:
            ends.setdefault(tuple(anchor.split("/", 1)), []).append(e)
        elif anchor in home:
            ends.setdefault(home[anchor], []).append(e)
        else:
            sys.exit(f"remake_ui.py: {e['name']} is placed after {anchor}, which is no OoTR setting")

    def section(tab_name, sec_name):
        tab = next((t for t in tabs if t["name"] == tab_name), None)
        if tab is None:
            mt = next((t for t in mapping["Tabs"] if t["name"] == tab_name), {})
            tab = {"name": tab_name, "text": mt.get("text") or tab_name, "sections": []}
            tabs.append(tab)
        sec = next((s for s in tab["sections"] if s["name"] == sec_name), None)
        if sec is None:
            mt = next((t for t in mapping["Tabs"] if t["name"] == tab_name), {})
            ms = next((s for s in mt.get("sections", []) if s["name"] == sec_name), {})
            sec = {"name": sec_name, "text": remake_ui.SECTION_TEXT.get(sec_name) or ms.get("text") or sec_name,
                   "settings": []}
            mine = ootr_order.get((tab_name, sec_name))
            at = len(tab["sections"])
            for i, s in enumerate(tab["sections"]):  # OoTR's sections in OoTR's order, ours before "Advanced"
                theirs = ootr_order.get((tab_name, s["name"]))
                if (mine is not None and theirs is not None and theirs > mine) or s["name"] == "advanced":
                    at = i
                    break
            tab["sections"].insert(at, sec)
        return sec
    for key in ends:
        section(*key)

    def expand(name):
        out = []
        for e in after.get(name, []):
            out += [e] + expand(e["name"])
        return out
    for t in tabs:
        for sec in t["sections"]:
            new = []
            for e in sec["settings"] + ends.get((t["name"], sec["name"]), []):
                new += [e] + expand(e["name"])
            sec["settings"] = new
    got = [e["name"] for t in tabs for s in t["sections"] for e in s["settings"] if e["name"] in ours]
    if sorted(got) != sorted(ours):
        sys.exit(f"remake settings placed twice or not at all: {sorted(set(ours) ^ set(got))}")


def main(out=OUT):
    import generate
    generate.ootr()
    generate.register_remake_tricks()
    import world_settings
    from SettingsList import SettingInfos
    infos = SettingInfos.setting_infos
    owns, remake, remake_default = {}, {}, {}
    for name in generate.enabled_plugins():
        m = importlib.import_module(f"parity.{name}")
        for k, ok in getattr(m, "OWNS", {}).items():
            owns[k] = None if ok is None else list(ok)
        remake.update(getattr(m, "REMAKE_SETTINGS", {}))
        remake_default.update(getattr(m, "REMAKE_DEFAULTS", {}))
    prober = Prober(generate)
    enablers = _enablers(infos)
    probed = {"values": 0, "dropped": []}

    def probe(name, value):
        """Can the remake make name = value (with its parent turned on)?"""
        over = {name: value}
        if name in enablers:
            parent, pv = enablers[name]
            over.setdefault(parent, pv)
        probed["values"] += 1
        return prober.ok(over)
    aliases = json.load(open(os.path.join(HERE, "config", "setting_aliases.json"), encoding="utf-8"))["names"]
    familiar = {v["key"]: (k, v) for k, v in aliases.items() if "item" not in v}  # not a table's entry names

    def allowed(name):
        """None means any value, a list means only those, False means not offered."""
        if name in owns:  # a plugin that applies it beats world_settings' tables, same as in generate
            return owns[name]
        if name in world_settings.REMAKE_ONLY:
            return False
        for table in (world_settings.APPLIED, world_settings.SUPPORTED):
            if name in table:
                return list(table[name])
        if name in world_settings.GENERATOR_ANY or name in world_settings.STARTING:
            return None
        return False

    def entry(name):
        info = infos.get(name)
        if info is None or name in EXCLUDE or (not info.shared and name not in owns):  # cosmetics aren't
            return None                                                                # "shared", a plugin owns them
        ok = allowed(name)
        if ok is False:
            return None
        tip = " ".join((info.gui_tooltip or "").split())
        for typo, fixed in TOOLTIP_TYPOS.items():  # typos in OoTR's own text, vendor/ootr stays untouched
            tip = tip.replace(typo, fixed)
        tip = REMAKE_TIPS.get(name, tip)
        e = {"name": name, "label": info.gui_text or name, "tooltip": tip, "default": _plain(info.default)}
        if name in REMAKE_DEFAULTS:
            e["default"], e["tooltip"] = REMAKE_DEFAULTS[name]
        rules = _disable_rules(info)
        if rules:
            e["disable"] = rules
        choices = getattr(info, "choices", None) or {}
        test = ok is None and name not in NO_PROBE  # "any value" or "checked by the plugin", so try each value
        if info.type is bool:
            e["type"] = "bool"
            if ok is not None and len(ok) == 1:
                return None  # pinned
            if test and not (probe(name, True) and probe(name, False)):
                probed["dropped"].append(name)
                return None
        elif info.type is int:
            e["type"] = "int"
            gp = getattr(info, "gui_params", {}) or {}
            lo, hi = gp.get("min", 0), gp.get("max", 1000)
            legal = [v for v in (getattr(info, "choice_list", None) or []) if isinstance(v, int)]
            step = int(gp.get("step", 1) or 1)
            if legal:  # OoTR's values, e.g. starting_hearts 3-20 or shop prices in steps of 5
                lo, hi = max(lo, min(legal)), min(hi, max(legal))
                if step > 1:
                    e["step"] = step
            if name in WIDER:  # the remake's wider range, OoTR's values are inside it
                lo, hi = WIDER[name][0]
                e["tooltip"] = WIDER[name][1]
            if ok is not None:
                lo, hi = max(lo, min(ok)), min(hi, max(ok))
            elif test:
                span = [v for v in (range(lo, hi + 1, step) if (hi - lo) // step <= 30 else
                                    sorted({lo, hi, info.default, *range(lo, hi + 1, max(step, (hi - lo) // 6 // step * step))}))
                        if not legal or v in legal]
                good = [v for v in span if probe(name, v)]
                if len(good) <= 1:
                    probed["dropped"].append(name)
                    return None
                lo, hi = min(good), max(good)
            if lo >= hi:
                return None  # pinned
            e["min"], e["max"] = lo, hi
        elif info.type is list:
            e["type"] = "list"
            vals = [[str(k), str(v)] for k, v in choices.items()]
            if test:
                vals = [kv for kv, k in zip(vals, choices) if probe(name, [k])]
                if not vals:
                    probed["dropped"].append(name)
                    return None
            e["choices"] = vals
        elif info.type is dict:
            e["type"] = "dict"
        else:
            e["type"] = "choice"
            vals = [[str(k), str(v)] for k, v in choices.items() if (ok is None or k in ok)
                    and (not test or k == info.default or probe(name, k))]
            if len(vals) <= 1:
                return None  # nothing to choose
            e["choices"] = vals
        return e
    mapping = json.load(open(os.path.join(HERE, "vendor", "ootr", "data", "settings_mapping.json"), encoding="utf-8"))
    tabs, seen = [], set()
    for t in mapping["Tabs"]:
        if t["name"] in SKIP_TABS:
            continue
        secs = []
        for sec in t.get("sections", []):
            if sec.get("exclude_from_electron") or sec["name"].endswith("_patcher"):
                continue
            items = [x for x in (entry(n) for n in sec.get("settings", []) if n not in seen) if x]
            seen.update(x["name"] for x in items)
            if items:
                secs.append({"name": sec["name"], "text": sec.get("text") or "", "settings": items})
        more = [x for x in (entry(n) for n in EXTRA_IN_TAB.get(t["name"], []) if n not in seen) if x]
        if more:
            seen.update(x["name"] for x in more)
            for x in more:
                x["label"], x["tooltip"] = EXTRA_LABELS.get(x["name"], (x["label"], x["tooltip"]))
            secs.append({"name": "advanced", "text": "Advanced", "settings": more})
        if secs:
            tabs.append({"name": t["name"], "text": t.get("text") or t["name"], "sections": secs})
    # If a parent the app doesn't show always turns a setting off (the parent keeps its base value), that setting
    # would never do anything. shuffle_gerudo_fortress_heart_piece is one, it needs interior/hideout entrance shuffles
    # the remake doesn't have.
    shown = {e["name"] for t in tabs for s in t["sections"] for e in s["settings"]}
    for parent, info in infos.items():
        if parent in shown:
            continue
        value = prober.base.get(parent, info.default)
        for rule in _disable_rules(info):
            w = rule["when"]
            hit = (str(value) != w[1:]) if w.startswith("!") else (str(value) == w)
            if not hit:
                continue
            for t in tabs:
                for sec in t["sections"]:
                    gone_here = [e["name"] for e in sec["settings"] if e["name"] in rule["settings"]]
                    if gone_here:
                        probed["dropped"] += [f"{n} (off by {parent})" for n in gone_here]
                        sec["settings"] = [e for e in sec["settings"] if e["name"] not in rule["settings"]]
    for t in tabs:
        t["sections"] = [s for s in t["sections"] if s["settings"]]
    # A parent value that's only there for a dependent the remake can't use isn't offered either, e.g. Master Quest
    # "specific" when no dungeon can be MQ.
    gone = set(probed["dropped"])
    by_value = {}
    for dep, (parent, value) in enablers.items():
        by_value.setdefault((parent, str(value)), []).append(dep)
    for t in tabs:
        for sec in t["sections"]:
            for e in sec["settings"]:
                if e["type"] != "choice":
                    continue
                keep = []
                for k, label in e["choices"]:
                    deps = by_value.get((e["name"], k), [])
                    if deps and all(d in gone for d in deps) and k != str(e["default"]):
                        probed["dropped"].append(f"{e['name']}={k}")
                        continue
                    keep.append([k, label])
                e["choices"] = keep
            sec["settings"] = [e for e in sec["settings"] if e["type"] != "choice" or len(e["choices"]) > 1]
    # The remake's own settings, meaning REMAKE_SETTINGS with their values plus the ones plugins read through
    # REMAKE_KEYS
    import no_vanilla
    from parity import _hints_extra
    remake.setdefault(no_vanilla.SETTING, (False, True))
    # Same default as the generator (off). The app only writes a setting when it differs from the schema's default, so
    # the two have to agree.
    remake_default.setdefault(no_vanilla.SETTING, no_vanilla.DEFAULT)
    extra = {"remake_shuffle_master_sword": ((False, True), False), "remake_silver_rupee_items": ((True, False), True),
             "remake_extra_hints": (list, []), "remake_trap_weights": (None, {"ice": 1})}
    for name in generate.enabled_plugins():
        m = importlib.import_module(f"parity.{name}")
        for k in getattr(m, "REMAKE_KEYS", None) or ():
            if k not in remake:
                vals, default = extra.get(k, (None, None))
                remake[k] = vals
                remake_default.setdefault(k, default)
    placed = []  # (anchor, entry) pairs, the anchor says where each remake setting shows (remake_ui.UI's first field)
    unlabelled, nodefault = [], []
    order = {k: i for i, k in enumerate(remake_ui.UI)}
    for k, vals in sorted(remake.items(), key=lambda kv: (order.get(kv[0], len(order)), kv[0])):
        ui = remake_ui.UI.get(k)
        fam = familiar.get(k)
        if ui is None:
            unlabelled.append(k)
            ui = (remake_ui.REMAKE_HOME, (fam[0] if fam else k).replace("remake_", "").replace("_", " ").capitalize(),
                  None, (fam[1].get("source") if fam else "") or "")
        anchor, label, names, tip = ui
        if k in remake_default:
            dflt = remake_default[k]
        elif k in remake_ui.DEFAULTS:
            dflt = remake_ui.DEFAULTS[k]
        else:
            nodefault.append(k)
            dflt = vals[0] if isinstance(vals, (list, tuple)) and vals else None
        e = {"name": k, "label": label, "tooltip": tip, "default": _plain(dflt)}
        if vals is list:
            e["type"] = "list"
            e["choices"] = [[h, h.replace("_", " ").capitalize()] for h in _hints_extra.HINTS]
        elif not isinstance(vals, (list, tuple)):  # any value, like the trap weights table, is written as JSON
            e["type"] = "json"
        elif set(map(str, vals)) <= {"True", "False"}:
            e["type"] = "bool"
        elif all(isinstance(v, int) and not isinstance(v, bool) for v in vals) and \
                sorted(vals) == list(range(min(vals), max(vals) + 1)):
            e["type"], e["min"], e["max"] = "int", min(vals), max(vals)
        else:
            e["type"] = "choice"
            e["choices"] = [[str(v), (names or {}).get(str(v), str(v))] for v in vals]
        if k in remake_ui.TYPES:  # the plugin checks it itself, TYPES has the type and limits the app uses
            e.update({x: v for x, v in remake_ui.TYPES[k].items()})
            if e.get("choices") == "enemies":
                e["choices"] = _enemy_choices()
        if k in remake_ui.RULES:
            e["disable"] = remake_ui.RULES[k]
        if k == "remake_trap_weights":  # one number per kind, folded back by config/setting_aliases.json
            for kind in _trap_kinds():
                w = (dflt or {}).get(kind, 0)
                placed.append((anchor, {"name": f"remake_trap_weight_{kind}", "type": "int", "min": 0, "max": 100,
                                        "default": w,
                                        "label": remake_ui.TRAP_KIND_LABELS.get(kind, kind.capitalize()),
                                        "tooltip": remake_ui.TRAP_KIND_TIPS.get(kind, tip)}))
            continue
        placed.append((anchor, e))
    _place(tabs, placed, mapping)
    if nodefault:  # a wrong default would make the app write it, changing seeds the player didn't change
        sys.exit(f"remake settings without a known default (REMAKE_DEFAULTS or remake_ui.DEFAULTS): {nodefault}")
    if unlabelled:
        print(f"note: remake settings without a label in tools/release/remake_ui.py: {', '.join(unlabelled)}")
    import glitch_ui  # explains Logic Rules' Glitched, remake glitches get their own Detailed Logic section
    glitch_ui.apply(tabs)
    presets = []
    pd = os.path.join(HERE, "vendor", "ootr", "data", "presets_default.json")
    if os.path.exists(pd):
        presets = sorted(json.load(open(pd, encoding="utf-8")))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump({"format": 1, "tabs": tabs, "presets": presets}, open(out, "w", encoding="utf-8"), indent=1,
              ensure_ascii=False)
    n = sum(len(s["settings"]) for t in tabs for s in t["sections"])
    print(f"{out}: {len(tabs)} tabs, {n} settings; {probed['values']} values tried, not offered: "
          f"{', '.join(probed['dropped']) or 'none'}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else OUT)
