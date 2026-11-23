"""Parity plugin: hints from Ship of Harkinian (SoH) and the 3DS randomizer (OoT3DR) that neither OoTR's misc hints nor
remake_extra_hints (hints.py) give. Every one is a remake setting, off by default, and with all of them off the plugin
changes nothing (no hook installed, no plan section).

Game text it builds on: data/rando/extras_hints.json, built
by tools/rando/parity/_extras_hints_build.py ROMFS. Hint distributions: data/rando/hint_dists/*.json. I only read SoH
and OoT3DR as a factual reference (no code copied).

Settings (value: default first):
- remake_scrub_text_hint False | True (SoH Scrub Text Hint): each Business Scrub names what it sells. Every shuffled
  scrub's sale call (SimpleShopSub_Scrub_Business_OneTime, param SellerMessageId) shows its own message: a new label per
  scrub (and per tier of a progressive item) in EventFlowMsg/Enemy_Event, in every language, with the game's own item
  name and the vanilla offer's price run (the live SimpleShop_Price tag and its plural tags). The shops plugin builds
  the scrubs (tools/rando/shops.py plan_ops). This plugin wraps plan_ops for the seed and points that plan's sale calls
  at the new labels, so it sees exactly what the shops plugin sells. An ice trap's offer names OoTR's disguise for it
  (looks_like_item), spelled like the real item (SoH "Identical" names).
- remake_loach_hint False | True (SoH Loach Hint): the pond owner's prize line (MiniGame_Fishing Talk_152, "the bigger
  the fish, the fancier the prize") gets a page naming what keeping the Hyrule loach gives (OoTR's LH Loach Fishing,
  shuffle_loach_reward), with the game's own loach name in every language.
- remake_hint_distribution "off" | a SoH or OoT3DR Gossip Stone distribution: soh_useless, soh_balanced, soh_strong,
  soh_very_strong (SoH Hint Distribution), 3ds_useless, 3ds_balanced, 3ds_strong, 3ds_very_strong, 3ds_playthrough
  (OoT3DR Hint Distribution). The static ones become OoTR's own distribution (useless/balanced, whose weights are
  exactly those) or an OoTR custom distribution with that randomizer's weights, copies and dungeon limits
  (data/rando/hint_dists). With 3ds_playthrough every major item of the playthrough gets one hint on a stone the player
  can reach without that item, and the other stones are junk. OoT3DR's ignore list applies: tokens, hearts, small keys,
  Triforce pieces, own-dungeon boss keys, rewards when the altar names them, Light Arrows when Ganondorf does.
- remake_hint_specificity "area" | "exact" (OoT3DR Specificity, with 3ds_playthrough): the playthrough hints name the
  item's area (OoTR's random-hint wording) or its exact location (OoTR's always-hint wording). A location OoTR has no
  hint text for keeps the area.
- remake_bonus_gossip_hints False | True (OoT3DR Bonus Hints, with 3ds_playthrough): the Sun's Song and the six warp
  songs (in random order) get a hint too when the playthrough doesn't already name them.
"""
import copy
import difflib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(HERE, "tools"))
sys.path.insert(0, os.path.join(HERE, "tools", "rando"))
DATA_PATH = os.path.join(HERE, "data", "rando", "extras_hints.json")
DISTS = os.path.join(HERE, "data", "rando", "hint_dists")
OOTR_HINTS = os.path.join(HERE, "vendor", "ootr", "data", "Hints")

OWNS = {}
DIST_CHOICES = ("off", "soh_useless", "soh_balanced", "soh_strong", "soh_very_strong", "3ds_useless", "3ds_balanced",
                "3ds_strong", "3ds_very_strong", "3ds_playthrough")
# a remake value -> OoTR's own distribution (identical weights) or one of ours (data/rando/hint_dists)
OOTR_SAME = {"soh_useless": "useless", "3ds_useless": "useless", "3ds_balanced": "balanced",
             "3ds_playthrough": "useless"}  # playthrough: every stone junk first, then the playthrough hints
REMAKE_SETTINGS = {
    "remake_scrub_text_hint": (False, True),
    "remake_loach_hint": (False, True),
    "remake_hint_distribution": DIST_CHOICES,
    "remake_hint_specificity": ("area", "exact"),
    "remake_bonus_gossip_hints": (False, True),
}
REMAKE_DEFAULTS = {"remake_scrub_text_hint": False, "remake_loach_hint": False, "remake_hint_distribution": "off",
                   "remake_hint_specificity": "area", "remake_bonus_gossip_hints": False}
LOACH = "LH Loach Fishing"
SCRUB_TEXT_FILE = "EventFlowMsg/Enemy_Event.msbt"
LABEL_PREFIX = "Rando_ScrubHint_"
WIDTH = 46  # the game's text box, in Latin characters (CJK characters count 2), as _hints_extra wraps

# Each frame is an item line, a lead-in to the price, and an optional replacement for the text after it.
# The Spanish ("¿Te la quedas?") and Italian ("comprarlo") tails refer to the vanilla item's gender, so we swap them.
SCRUB_FRAMES = {
    "en": ("Ohhh, {item}! Shimmery glimmery!", "It's ", None),
    "de": ("Oooh, {item}! Wie das glänzt, wie das glitzert!", "Kostet nur ", None),
    "es": ("¡Aaah, {item}! ¡Reluce como una joya!", "Y solo vale ", ".{tag:5,0} ¿Trato hecho?"),
    "fr": ("Biii, {item} ! Ça brille de mille feux !", "Ça coûte ", None),
    "it": ("Ho qui {item}. Bello scintillante, per giunta!", "Costa ", ".{tag:5,0} Ti interessa?"),
    "nl": ("Ahhh, {item}! Glinsterend en glanzend!", "Voor slechts ", None),
    "pt": ("Aaah, {item}! Tinindo! Brilhando!", "Custa ", None),
    "pl": ("Ooo, {item}! Ale błyszczy!", "Kosztuje tylko ", None),
    "ru": ("О-о-о, {item}! Сверкает-блистает!", "", None),
    "ja": ("キラキラきらめく {item}", "", None),
    "ko": ("반짝반짝 빛나는 {item}은(는)", "", None),
    "zh_cn": ("闪闪发光的{item}！", "价格是", None),
    "zh_tw": ("亮晶晶的{item}。", "價格是", None),
}
# the loach as the subject of _hints_extra's reward frame ("{what}...\nthe reward: {item}!"), with each language's
# article for the game's own loach name (de die Schmerle, es/fr/pt feminine, it masculine)
LOACH_WHAT = {"en": "A {loach}", "de": "Eine {loach}", "es": "Una {loach}", "fr": "La {loach}", "it": "Un {loach}",
              "nl": "Een {loach}", "pt": "Uma {loach}", "pl": "{Loach}", "ru": "{Loach}", "ja": "{loach}",
              "ko": "{loach}", "zh_cn": "{loach}", "zh_tw": "{loach}"}
LOACH_TARGET = ("EventFlowMsg/MiniGame_Fishing.msbt", "Talk_152")

_data = None
_scrub = {"on": False, "plans": {}, "world": None}
_play = {"on": False, "exact": False, "bonus": False, "notes": []}


def data():
    global _data
    if _data is None:
        _data = json.load(open(DATA_PATH, encoding="utf-8"))
    return _data


def _remake(settings):
    return getattr(settings, "remake", None) or {}


def value(settings, key):
    return _remake(settings).get(key, REMAKE_DEFAULTS[key])


def active(settings):
    return {k: value(settings, k) for k in REMAKE_SETTINGS if value(settings, k) != REMAKE_DEFAULTS[k]}


# Settings
def check_settings(settings):
    out = []
    remake = _remake(settings)
    for k, v in remake.items():
        if k in REMAKE_SETTINGS:
            ok = REMAKE_SETTINGS[k]
            if v not in ok or isinstance(v, bool) != isinstance(ok[0], bool):
                out.append(f"{k} = {v!r}: extras_hints can make {', '.join(map(repr, ok))}")
            continue
        near = difflib.get_close_matches(k, list(REMAKE_SETTINGS), n=1, cutoff=0.85)
        if near:
            out.append(f"{k}: unknown remake setting; did you mean {near[0]}?")
    dist = remake.get("remake_hint_distribution", "off")
    if dist != "off" and dist in DIST_CHOICES:
        if getattr(settings, "hint_dist_user", None):
            out.append(f"remake_hint_distribution = {dist!r} with hint_dist_user: give one Gossip Stone distribution")
        elif getattr(settings, "hint_dist", "balanced") != "balanced":
            out.append(f"remake_hint_distribution = {dist!r} with hint_dist = {settings.hint_dist!r}: give one Gossip "
                       f"Stone distribution (leave hint_dist at its default, 'balanced')")
        if dist == "3ds_playthrough" and getattr(settings, "logic_rules", "glitchless") == "none":
            out.append("remake_hint_distribution 3ds_playthrough needs logic (OoT3DR: not compatible with No Logic)")
    if dist != "3ds_playthrough":
        for k in ("remake_hint_specificity", "remake_bonus_gossip_hints"):
            if k in remake and remake[k] != REMAKE_DEFAULTS[k]:
                out.append(f"{k} only applies to remake_hint_distribution '3ds_playthrough' (OoT3DR shows it there only)")
    if remake.get("remake_loach_hint") is True and getattr(settings, "shuffle_loach_reward", "off") == "off":
        out.append("remake_loach_hint names the Hyrule loach's prize, which only shuffle_loach_reward ('vanilla' or "
                   "'easy') randomizes; it is 'off'")
    return out


def untested(settings):
    out = []
    a = active(settings)
    if a.get("remake_scrub_text_hint"):
        out.append("extras_hints: remake_scrub_text_hint - new Enemy_Event labels, scrub sale calls' SellerMessageId")
    if a.get("remake_loach_hint"):
        out.append("extras_hints: remake_loach_hint - a page after MiniGame_Fishing Talk_152")
    if "remake_hint_distribution" in a:
        out.append(f"extras_hints: remake_hint_distribution {a['remake_hint_distribution']} (Gossip Stone text as "
                   f"OoTR builds it)")
    return out


# Distributions (before OoTR builds the world)
def _dist_for(name):
    if name in OOTR_SAME:
        d = json.load(open(os.path.join(OOTR_HINTS, f"{OOTR_SAME[name]}.json"), encoding="utf-8"))
    else:
        d = json.load(open(os.path.join(DISTS, f"{name}.json"), encoding="utf-8"))
    d = copy.deepcopy(d)
    d["name"] = name
    return d


def before_build(settings):
    dist = value(settings, "remake_hint_distribution")
    if dist != "off":
        settings.hint_dist_user = _dist_for(dist)  # World reads it as an OoTR custom distribution
    _play.update(on=dist == "3ds_playthrough", exact=value(settings, "remake_hint_specificity") == "exact",
                 bonus=bool(value(settings, "remake_bonus_gossip_hints")), notes=[])
    if _play["on"]:
        _install_playthrough()
    _scrub["on"] = bool(value(settings, "remake_scrub_text_hint"))
    _scrub["plans"] = {}
    if _scrub["on"]:
        _install_scrub_wrapper()


# OoT3DR playthrough hints
IGNORED = {"Gold Skulltula Token", "Piece of Heart", "Piece of Heart (Treasure Chest Game)", "Heart Container",
           "Triforce Piece"}
REWARDS = {"Kokiri Emerald", "Goron Ruby", "Zora Sapphire", "Forest Medallion", "Fire Medallion", "Water Medallion",
           "Spirit Medallion", "Shadow Medallion", "Light Medallion"}
BONUS_WARPS = ["Prelude of Light", "Minuet of Forest", "Bolero of Fire", "Serenade of Water", "Requiem of Spirit",
               "Nocturne of Shadow"]


def _ignored(world, item):
    s = world.settings
    name = item.name
    if name in IGNORED or item.type in ("SmallKey", "HideoutSmallKey", "TCGSmallKey", "SilverRupee", "Event", "Shop"):
        return True
    if name.startswith(("Small Key", "Silver Rupee")):
        return True
    if item.type == "BossKey" and name != "Boss Key (Ganons Castle)" and s.shuffle_bosskeys == "dungeon":
        return True
    if name in REWARDS and "altar" in (s.misc_hints or []):
        return True
    if name == "Light Arrows" and "ganondorf" in (s.misc_hints or []):
        return True
    if name == "Boss Key (Ganons Castle)" and s.shuffle_ganon_bosskey not in (
            "remove", "vanilla", "dungeon", "regional", "overworld", "any_dungeon", "keysanity"):
        return True  # given by a condition (OoT3DR's LACS-* values)
    return False


def _hint_text(world, location, exact):
    from Hints import GossipText, HintArea, get_item_generic_name
    from HintList import get_hint, hintTable
    lang = world.language
    clearer = world.settings.clearer_hints
    item_text = get_hint(get_item_generic_name(location.item), lang, clearer).text
    if exact and location.name in hintTable:
        loc_text = get_hint(location.name, lang, clearer).text
        if "#" not in loc_text:
            loc_text = f"#{loc_text}#"
        return GossipText(lang.format_from_id("hint_text.always", {"location": loc_text, "item": item_text}), lang,
                          ["Red", "Green"], [location.name], [location.item.name],
                          prefix=lang.hint_text["gossip_prefix"])
    area = HintArea.at(location)
    if area.is_dungeon:
        return GossipText(lang.format_from_id("hint_text.hoards", {"location_text": area.text(lang, clearer),
                                                                   "item_text": item_text}),
                          lang, ["Red", "Green"], [location.name], [location.item.name],
                          prefix=lang.hint_text["gossip_prefix"])
    return GossipText(lang.format_from_id("hint_text.can_be_found",
                                          {"location_text": area.text(lang, clearer, preposition=True),
                                           "item_text": item_text}),
                      lang, ["Green", "Red"], [location.name], [location.item.name],
                      prefix=lang.hint_text["gossip_prefix"])


def playthrough_targets(spoiler, world, bonus):
    """The locations OoT3DR's playthrough distribution hints, in sphere order, then the bonus songs."""
    import random
    out = []
    for sphere in spoiler.playthrough.values():
        for loc in sphere:
            if loc.world.id != world.id or loc.item is None or loc.type in ("Event", "HintStone", "Hint"):
                continue
            if loc.item.majoritem and not _ignored(world, loc.item) and loc not in out:
                out.append(loc)
    if bonus:
        warps = list(BONUS_WARPS)
        random.shuffle(warps)
        have = {loc.item.name for loc in out}
        for name in ["Suns Song"] + warps:
            if name in have:
                continue
            spots = [loc for loc in world.get_filled_locations() if loc.item.name == name
                     and loc.type not in ("Event", "HintStone", "Hint")]
            if spots:
                out.append(random.choice(sorted(spots, key=lambda x: x.name)))
    return out


def _playthrough_hints(spoiler, world):
    from Hints import add_hint, gossipLocations
    if world.settings.hints == "none":
        return
    if not spoiler.playthrough:
        spoiler.create_playthrough()
    disabled = set(world.hint_dist_user.get("disabled") or [])
    groups = [[sid] for sid in sorted(spoiler.hints[world.id]) if gossipLocations[sid].name not in disabled]
    placed = 0
    for loc in playthrough_targets(spoiler, world, _play["bonus"]):
        if add_hint(spoiler, world, groups, _hint_text(world, loc, _play["exact"]), 1, [loc], force_reachable=True,
                    hint_type="always"):
            placed += 1
        else:
            _play["notes"].append(f"3ds_playthrough: no stone left reachable without {loc.item.name} ({loc.name})")
    _play["notes"].append(f"3ds_playthrough: {placed} playthrough hints, the other stones junk")


def _install_playthrough():
    import Main
    if getattr(Main.build_gossip_hints, "remake_playthrough", False):
        return
    original = Main.build_gossip_hints

    def build_gossip_hints(spoiler, worlds, _original=original):
        _original(spoiler, worlds)  # every stone junk (the distribution is OoTR's useless one), misc hints as usual
        if _play["on"]:
            for world in worlds:
                _playthrough_hints(spoiler, world)
    build_gossip_hints.remake_playthrough = True
    Main.build_gossip_hints = build_gossip_hints


# Text helpers
def _X():
    from . import _hints_extra as X
    return X


def _actor_name(actor, ui_lang):
    """The game's own name for pouch actor `actor` in `ui_lang`, or None. Besides _hints_extra's lookups, an Item_*
    get actor is also tried as the pouch entry it becomes (Item_Gauntlet_Goron is named as Armor_Child_Gauntlet_Goron)."""
    X = _X()
    if not actor:
        return None
    names = dict(X._names(ui_lang)["item"])
    names.update({k: v for k, v in X._load(X.DATA).get("item_names", {}).get(ui_lang, {}).items() if X._plain(v)})
    pouch = X._load(os.path.join(HERE, "data", "rando", "pouch_actors.json"))["actors"].get(actor, [None])[0]
    rest = actor.split("_", 1)[1] if "_" in actor else actor
    for a in (actor, actor.replace("TBox_", "Obj_"), actor.replace("TBox_", "Item_"), actor.replace("Shop_", "Item_"),
              pouch, f"Armor_Child_{rest}", f"Armor_Adult_{rest}", f"Weapon_{rest}"):
        if a and X._plain(names.get(a)):
            return X._plain(names[a])
    return None


def item_name(item, ui_lang, actor=None):
    """What the player is told they get: the game's own name of `actor` (a tier) or of OoTR item `item`."""
    X = _X()
    name = _actor_name(actor, ui_lang) if actor else None
    if name:
        return name
    name = X.item_name(item, ui_lang)
    if name == item and item != "Ice Trap":  # _hints_extra fell back to OoTR's English name: try the pouch entry
        name = _actor_name(X.actor_of(item), ui_lang) or name
    return name


def _pages(lines):
    PAGE = "{tag:0,4}"
    return PAGE.join("\n".join(lines[i:i + 3]) for i in range(0, len(lines), 3))


def scrub_markup(name, lang):
    """The whole offer message naming `name` in archive `lang` (speaker, the item line(s), the price line)."""
    X = _X()
    key = X.LANG[lang]
    item_line, before_price, after = SCRUB_FRAMES[key]
    offer = data()["scrub_offer"][lang]
    line = item_line.format(item=f"\x01{name}\x02")
    if lang == "USfr":  # Canadian French writes no space before ! ? : (the game's own USfr text)
        line = re.sub(r" ([!?:])", r"\1", line)
    lines = X._wrap_line(line, key, WIDTH)
    tail = after if after is not None else offer["after"]
    price_line = before_price + offer["price"] + tail
    lines.append(price_line)
    mk = _pages(lines).replace("\x01", X.HI).replace("\x02", X.LO)
    return offer["lead"] + mk


# Scrubs (wrapping the shops plugin's plan)
def _slug(name):
    return re.sub(r"[^A-Za-z0-9]", "", name.title())


def _install_scrub_wrapper():
    import shops as shop_tools  # tools/rando/shops.py, as the shops plugin imports it
    if getattr(shop_tools.plan_ops, "remake_scrub_text_hint", False):
        return
    original = shop_tools.plan_ops

    def plan_ops(assignments, *args, _original=original, **kw):
        plan = _original(assignments, *args, **kw)
        if _scrub["on"]:
            looks = kw.get("looks_like") or (args[2] if len(args) > 2 else None) or {}
            appearance = kw.get("appearance") or (args[1] if len(args) > 1 else None) or "anything"
            scrub_hint_ops(plan, assignments, looks, appearance)
        return plan
    plan_ops.remake_scrub_text_hint = True
    shop_tools.plan_ops = plan_ops


def _disguise(location, appearance):
    """A stand-in name for an ice trap OoTR gave no looks_like_item (junk turned into traps after its model pass). It's
    the kind OoTR's ice_trap_appearance asks for, picked from this seed's items by the location's name so it's
    stable."""
    from ItemPool import remove_junk_items
    world = _scrub.get("world")
    junk = sorted(n for n in remove_junk_items if n != "Ice Trap")
    major = sorted({loc.item.name for loc in world.get_filled_locations() if loc.item.majoritem
                    and loc.item.type == "Item"}) if world is not None else []
    pool = major if appearance == "major_only" else junk if appearance == "junk_only" else major + junk
    pool = pool or junk
    return pool[sum(map(ord, location)) % len(pool)]


def _display(item, looks, location="", appearance="anything"):
    """(OoTR item named, [pouch actor per tier] or None): what a scrub's offer names for OoTR item `item`."""
    import shops as shop_tools
    if item == "Ice Trap":
        return (looks or _disguise(location, appearance)), None
    tiers = (shop_tools.shop_map()["scrub_items"].get(item) or {}).get("tiers")
    return item, tiers


def _names_per_lang(item, tier_actor):
    return {lang: item_name(item, lang, tier_actor) for lang in data()["scrub_offer"]}


def scrub_hint_ops(plan, assignments, looks_like, appearance="anything"):
    """Points every shuffled scrub's sale call(s) in `plan` (tools/rando/shops.py plan_ops output) at its own message
    naming the item, and adds those messages (every language) to plan["text"]. What it did goes in
    plan["_extras_hints_scrubs"] for verify()."""
    import shops as shop_tools
    sm = shop_tools.shop_map()["locations"]
    events = plan.setdefault("events", [])
    record = {}
    texts = []
    for name, (item, _price) in sorted(assignments.items()):
        loc = sm.get(name)
        if not loc or loc["kind"] != "scrub" or loc["mode"] != "full" or shop_tools._keeps_remake_vanilla(loc, item):
            continue
        e = loc["edit"]
        shown, tiers = _display(item, looks_like.get(name), name, appearance)
        labels = {}  # tier index (or None) -> label

        def label_for(tier, tiers=tiers, shown=shown, name=name, labels=labels):
            if tier not in labels:
                lab = f"{LABEL_PREFIX}{_slug(name)}" + (f"_{tier}" if tier is not None and len(tiers or []) > 1 else "")
                labels[tier] = lab
                actor = tiers[tier] if tiers is not None and tier is not None else None
                for lang, nm in _names_per_lang(shown, actor).items():
                    mk = scrub_markup(nm, lang)
                    plain = re.sub(r"\{tag:0,4\}", "\n", mk)
                    plain = re.sub(r"\{tag:[^}]*\}", "", plain)
                    texts.append({"lang": lang, "file": SCRUB_TEXT_FILE, "label": lab, "markup": mk, "text": plain,
                                  "add": True, "note": f"remake_scrub_text_hint {name}"})
            return f"{SCRUB_TEXT_FILE[:-5]}:{labels[tier]}"
        done = []
        if e.get("converted"):
            graph = next((op for op in events if op.get("add_graph") == e["graph"]), None)
            if graph is None:
                raise RuntimeError(f"extras_hints: {name}: the shops plan has no {e['graph']} graph")
            idx = next((k[3:] for k, n in graph["nodes"].items() if k.startswith("key")
                        and (n.get("params") or {}).get("Value") == e["key"]), None)
            if idx is None:
                raise RuntimeError(f"extras_hints: {name}: no key node for {e['key']} in {e['graph']}")
            for nname, node in graph["nodes"].items():
                m = re.fullmatch(rf"(?:sell{idx}|sale{idx}_(\d+))", nname)
                po = node.get("params_over") or {}
                if m and "SellerMessageId" in po:
                    tier = int(m.group(1)) if m.group(1) is not None else (0 if tiers else None)
                    po["SellerMessageId"] = label_for(tier)
                    done.append({"graph": e["graph"], "node": nname, "label": po["SellerMessageId"]})
        else:
            for op in events:
                if op.get("add_graph") in (e["graph"], e["graph"] + "_Ice"):
                    for nname, node in op["nodes"].items():
                        po = node.get("params_over") or {}
                        if "SellerMessageId" in po:
                            po["SellerMessageId"] = label_for(0 if tiers else None)
                            done.append({"graph": op["add_graph"], "node": nname, "label": po["SellerMessageId"]})
            if item != "Ice Trap":
                for k, c in enumerate(e["calls"][:len(tiers or [None])]):
                    lab = label_for(k if tiers else None)
                    op = next((x for x in events if x.get("event") == c["event"] and x.get("param") == "SellerMessageId"
                               and x.get("file") == e["scene"]), None)
                    if op is None:
                        events.append({"file": e["scene"], "flowchart": e["scene"], "event": c["event"],
                                       "param": "SellerMessageId", "value": lab,
                                       "note": f"remake_scrub_text_hint {name}"})
                    else:
                        op["value"] = lab
                    done.append({"event": c["event"], "label": lab})
        if not done:
            raise RuntimeError(f"extras_hints: {name}: found no sale call of this scrub in the shops plan")
        record[name] = {"scene": e["scene"], "item": item, "names": shown, "calls": done}
    if record:
        plan.setdefault("text", []).extend(texts)
        plan["_extras_hints_scrubs"] = record
        plan["_verify_plugins"] = ["extras_hints"]
        _scrub["plans"].update(record)
    return plan


# Loach
def loach_ops(world):
    X = _X()
    try:
        loc = world.get_location(LOACH)
    except KeyError:
        return []
    if loc.item is None:
        return []
    item = loc.item.name
    f, lb = LOACH_TARGET
    names = data()["loach"]

    def frames(lang):
        key = X.LANG[lang]
        nm = names[lang]
        what = LOACH_WHAT[key].format(loach=nm, Loach=nm[:1].upper() + nm[1:])
        return [X.reward_text(None, item_name(item, lang), lang, what=what)]
    ops = []
    for lang, markup in sorted(data()["messages"][f"{f}:{lb}"].items()):
        new = "{tag:0,4}".join(X.page_markup(t, X.LANG[lang]) for t in frames(lang))
        full = markup + "{tag:0,4}" + new
        plain = re.sub(r"\{tag:0,4\}", "\n", full)
        plain = re.sub(r"\{tag:[^}]*\}", "", plain)
        ops.append({"lang": lang, "file": f, "label": lb, "markup": full, "text": plain,
                    "note": "remake_loach_hint"})
    return ops


# Plan
def world_plan(settings, world):
    a = active(settings)
    if not a:
        return {}
    _scrub["world"] = world  # the shops plugin's plan comes after this one (plugins run by name)
    out = {}
    if a.get("remake_loach_hint"):
        ops = loach_ops(world)
        if ops:
            out["text"] = ops
    if "remake_hint_distribution" in a:
        out["_notes_extras_hints"] = [f"remake_hint_distribution {a['remake_hint_distribution']}"
                                      + (f" ({value(settings, 'remake_hint_specificity')} hints"
                                         + (", bonus songs" if _play["bonus"] else "") + ")"
                                         if _play["on"] else "")] + list(_play["notes"])
    return out


# Read-back
def verify(patch, plan, romfs):
    """Read the built scrub scene and text back: every shuffled scrub's sale call names its own message, and that
    message exists in every language with the item's name and the live price tag."""
    from evfl import Evfl
    from romtools import Romfs
    import msbt
    rec = plan.get("_extras_hints_scrubs") or {}
    if not rec:
        return []
    bad = []
    fs = Romfs(romfs, os.path.join(HERE, "original"), [patch])
    scenes = {}
    for name, r in sorted(rec.items()):
        sc = r["scene"]
        if sc not in scenes:
            d = os.path.join(patch, "Event", "EventFlow")
            fn = sorted(x for x in os.listdir(d) if re.match(re.escape(sc) + r"(\.\d{3})?\.bfevfl\.zs$", x)) \
                if os.path.isdir(d) else []
            if not fn:
                bad.append(f"scrub hint {name}: the patch has no {sc} scene")
                scenes[sc] = None
                continue
            fc = Evfl(fs.read("Event/EventFlow/" + fn[-1])).flowcharts[0]
            scenes[sc] = {e["name"]: e for e in fc["events"]}
        ev = scenes[sc]
        if ev is None:
            continue
        for c in r["calls"]:
            step = c.get("event") or f"{c['graph']}_{c['node']}"
            e = ev.get(step)
            got = (((e or {}).get("params") or {}).get("items") or {}).get("SellerMessageId", {}).get("value")
            if got != c["label"]:
                bad.append(f"scrub hint {name}: {sc} {step} SellerMessageId = {got!r}, planned {c['label']!r}")
    labels = {c["label"].split(":", 1)[1] for r in rec.values() for c in r["calls"]}
    for lang in msbt.archives(romfs):
        m = msbt.Msbt(msbt.read_archive(fs, lang)[SCRUB_TEXT_FILE])
        for lab in sorted(labels):
            if lab not in m.labels:
                bad.append(f"scrub hint {lang}: no message {lab}")
            elif "{tag:2,12," not in m.markup(lab):
                bad.append(f"scrub hint {lang}: {lab} lost its price tag")
    return bad
