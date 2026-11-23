"""Parity plugin for hints and text: OoT Randomizer's misc hints, clearer_hints, item_hints, custom hint
distributions (hint_dist_user), text_shuffle, show_seed_info / user_message and password_lock.

Where OoTR builds a hint text we use OoTR's (Hints.build_misc_item_hints, build_boss_string,
build_bridge_reqs_string, build_ganon_boss_key_string, the item and area names of HintList / HintArea), taken
without a ROM by _hints_ootr.capture. Where OoTR's N64 message has no remake counterpart it's worded for the
remake's own messages. Names are the remake's place and item names (data/rando/hints_names.json). Where each hint
shows up is in data/rando/hints_targets.json.

Misc hints (settings.misc_hints):
  altar               Temple of Time altar (the remake's altar sign, both ages): where the Spiritual Stones and
                      Medallions are (a localized list in every language), the Door of Time, rainbow bridge and
                      Ganon's Boss Key conditions as the remake applies them (boss defeats, not stones/medallions)
  ganondorf           Ganondorf's last line before the battle: where the Light Arrows are
  dampe_diary         Dampe's diary (adult): where the Hookshot is
  10..100_skulltulas  the cursed father's "collect N tokens" goal lines name each reward
  frogs2              the frogs' ocarina game explanation names its reward
  big_poes            the poe buyer names his bottle reward
  skull_mask, mask_of_truth  the Deku Theater sign names the rewards
  unique_merchants    the Mirage Desert carpet merchant names what he sells (shuffle_expensive_merchants)
  warp_songs_and_owls the warp song prompts and owl rides name their destination when those are shuffled
                      (vanilla destinations: the game's own text is already right)
  mask_shop           no text: OoTR's shuffled mask shop shelf; nothing to do while the masks stay unshuffled
Gossip Stones: each OoTR stone's hint goes to the remake stone standing where OoTR put it. That's
data/rando/hints_stones.json, built by _hints_stones.py from the level files, and it replaces generate.py's
pairing by area name. OoTR stones the remake doesn't have are kept out of OoTR's stone set, and the remake's extra
stones are added to it in their real regions (data/rando/logic/hints.json), so OoTR fills every stone that
exists, as usual.
OoTR's text is English, and the other 15 languages get the same English hint text (the place and item names of
the altar list are in each language). Text ops carry both "markup" (colours and page breaks, which need
make_patch.py support) and "text" (what make_patch.py writes today).
remake_extra_hints (remake setting, a list, default empty) adds hints beyond OoTR's, from Ship of Harkinian's
static hints and the 3DS randomizer's fishing hint (_hints_extra.py):
  mido      Mido's blocking lines: where the Kokiri Sword is
  saria     Saria's Song call and Saria at the Sacred Grove: where the magic meter is
  sheik     Sheik by the Master Sword pedestal: what Zelda's moat gift and the moat song give
  biggoron  Biggoron's waiting lines: what the Claim Check gives
  malon     adult Malon's obstacle-course lines: what Link's house cow gives
  anju      the cucco lady's request (its fixed "empty bottle" is rewritten): her reward
  archery   the horseback archery rules (fixed "Piece of Heart" / "quiver" rewritten): the two prizes
  fishing   the pond owner's prize lines (fixed "heart-shaped" / "golden" rewritten): the child and adult prizes
  merchants Medigoron, Granny and the bean salesman name what they sell (when it is shuffled)
  fishing_pole  (with remake_shuffle_fishing_pole) the owner's "no rod" line says where the pole is (extras_npcs.py)
  poe_collector, skulltula_100, carpet_merchant  OoTR's big_poes, 100_skulltulas and unique_merchants misc hints
The sentence frames are translated into every language the game ships, and item and place names are the game's
own per language. OoTR's misc hints that the three aliases turn on stay in English, the way OoTR writes them.
Business Scrubs aren't covered. Their offer is one fixed message per vanilla item, shared by every scrub selling
it, and the scrub's name tag reads the placement's lookup key, not the item sold.
"""
import gc
import re
import sys

from . import _hints_ootr as O
from . import _hints_text as T

MISC_SUPPORTED = {"altar", "ganondorf", "dampe_diary", "warp_songs_and_owls", "10_skulltulas", "20_skulltulas",
                  "30_skulltulas", "40_skulltulas", "50_skulltulas", "100_skulltulas", "frogs2", "mask_shop",
                  "unique_merchants", "big_poes", "skull_mask", "mask_of_truth"}
OWNS = {
    "misc_hints": None,                 # checked in check_settings (a list)
    "clearer_hints": (True, False),
    "item_hints": None,                 # OoTR's own (the 'item' / 'named-item' hint types)
    "hint_dist_user": None,             # OoTR's own (a custom hint distribution)
    "text_shuffle": ("none", "except_hints", "complete"),
    "show_seed_info": (True, False),
    "user_message": None,
    # password_lock belongs to the story plugin (parity/_gaps_password.py)
}
SKULL_GOALS = {"10_skulltulas": 10, "20_skulltulas": 20, "30_skulltulas": 30, "40_skulltulas": 40,
               "50_skulltulas": 50, "100_skulltulas": 100}
_pending = {"ops": [], "notes": []}


# Settings
EXTRA_KEY = "remake_extra_hints"
REMAKE_KEYS = (EXTRA_KEY,)  # remake settings this plugin reads (generate.unknown_remake_settings)


def extra_hints(settings):
    """remake_extra_hints: the hints beyond OoTR's this seed shows (default none)."""
    return list((getattr(settings, "remake", None) or {}).get(EXTRA_KEY, []) or [])


def check_settings(settings):
    _install_text_guard()
    problems = []
    from . import _hints_extra as X
    raw = (getattr(settings, "remake", None) or {}).get(EXTRA_KEY, [])
    if not isinstance(raw, list):
        problems.append(f"{EXTRA_KEY}: a list of {', '.join(X.HINTS)}")
    else:
        bad = sorted(set(raw) - set(X.HINTS))
        if bad:
            problems.append(f"{EXTRA_KEY}: unknown {bad} (the plugin has {', '.join(X.HINTS)})")
    problems += _extras_plugin_problems(settings)
    for h in settings.misc_hints or []:
        if h not in MISC_SUPPORTED:
            problems.append(f"misc_hints {h!r}: no remake counterpart yet (tools/rando/parity/hints.py)")
    masks = {"Goron Mask", "Zora Mask", "Gerudo Mask"} & set(getattr(settings, "shuffle_child_trade", []) or [])
    if "mask_shop" in (settings.misc_hints or []) and masks:
        problems.append(f"misc_hints 'mask_shop' with {', '.join(sorted(masks))} shuffled: the remake's mask shop "
                        f"shelves can't show a locked item yet")
    if len((getattr(settings, "user_message", "") or "").strip()) > 42:
        problems.append("user_message: at most 42 characters (OoTR's limit)")
    if getattr(settings, "text_shuffle", "none") != "none":
        from . import _hints_shuffle
        if _hints_shuffle.romfs() is None:
            problems.append("text_shuffle needs the game's text: set REMAKE_ROMFS to the romfs folder")
    problems += _stone_problems(settings)
    return problems


def _extras_plugin_problems(settings):
    """Default-deny for the extras plugin's settings. If a seed turns one on while extras_npcs.py doesn't run (it's
    not in config/plugins.json), nothing would build it, so we refuse it instead of ignoring it."""
    remake = getattr(settings, "remake", None) or {}
    if not any(k.startswith(("remake_shuffle_", "remake_fishsanity")) for k in remake) \
            and "fishing_pole" not in extra_hints(settings):
        return []
    import generate  # tools/rando/generate.py
    if "extras_npcs" in generate.enabled_plugins():
        return []
    from . import extras_npcs
    on = sorted(k for k, v in remake.items()
                if k in extras_npcs.REMAKE_SETTINGS and v != extras_npcs.REMAKE_DEFAULTS[k])
    return [f"{k} = {remake[k]!r}: needs the extras_npcs plugin (RANDO_PLUGINS=+extras_npcs)" for k in on]


def _stone_problems(settings):
    """The stone pairing's data must agree with the logic file that adds the extra stones, and a plando can't
    name a stone the remake doesn't have."""
    import json
    import os
    from . import _hints_stones as S
    problems = S.check_plando(settings)
    try:
        logic = json.load(open(S.LOGIC, encoding="utf-8"))
    except OSError:
        return problems + [f"{os.path.relpath(S.LOGIC, S.HERE)} missing: run tools/rando/parity/_hints_stones.py"]
    for e in S.load()["extra"]:
        if e["location"] not in logic.get("new_locations", {}) or e["location"] not in logic.get("regions", {}).get(e["region"], {}).get("locations", {}):
            problems.append(f"{e['stone']}: {e['location']} is not in data/rando/logic/hints.json: run "
                            f"tools/rando/parity/_hints_stones.py")
    return problems


def before_build(settings):
    """Makes OoTR's Gossip Stone set match the remake's, with the absent stones out and the remake's extra stones in
    (_hints_stones.install)."""
    from . import _hints_stones as S
    S.install()


def before_fill(world, settings):
    """The extra stones follow their twins in the hint distribution's stone lists, like coop's 'disabled'
    (_hints_stones.follow_twins). OoTR reads those lists when it builds the hints, after the fill."""
    from . import _hints_stones as S
    S.follow_twins(world)


# Text ops
def _box():
    return T.targets()["box"]


def _pages(control, width=None, player="Link"):
    box = _box()
    return T.wrap(T.tokens(T.remake_names(control), player), width or box["width"], box["lines"])


def _message_ops(file, label, new_pages_for, keep_pages=(), replace_pages=None, note="", leftover="spread",
                 width=None):
    """Text ops for one message in every language. new_pages_for(lang) -> control text (or a list of control
    texts, one per page)."""
    ops = []
    for lang, markup in sorted(T.vanilla(file, label).items()):
        control = new_pages_for(lang)
        if control is None:
            continue
        if isinstance(control, list):
            control = "\x04".join(control)
        w = width or (_box()["width_small"] if "{tag:0,2,5000}" in markup else _box()["width"])
        pages = _pages(control, w, T.names(lang)["player"])
        full, text, warning = T.build(markup, pages, keep_pages, replace_pages, w, leftover)
        op = {"lang": lang, "file": file, "label": label, "text": text, "markup": full}
        if note:
            op["note"] = note
        ops.append(op)
        # make_patch writes "markup" when an op has it, page breaks included, so the plain-text fallback's warning
        # (`warning`) doesn't apply. What the player sees is the markup's boxes.
        worst = max(page.count("\n") + 1 for page in full.split("{tag:0,4}"))
        if worst > 3 and lang == "USen":
            _pending["notes"].append(f"{file}:{label}: {worst} lines in one box")
    return ops


def _target_ops(key, new_pages_for, note=""):
    spec = T.targets()["targets"][key]
    ops = []
    for s in [spec] + spec.get("also", []):
        ops += _message_ops(s["file"], s["label"], new_pages_for, s.get("keep_pages", ()), s.get("replace_pages"),
                            note or key, s.get("leftover", spec.get("leftover", "spread")))
    return ops


# Misc hints
def altar_ops(world):
    """The remake's altar sign: one message for both ages, so OoTR's child and adult texts are joined."""
    import Hints
    from HintList import get_hint
    from ItemList import REWARD_COLORS
    s = world.settings
    lang = world.language
    include_rewards = "compass_reward" not in (s.enhance_map_compass or [])
    names = T._load(T.NAMES)

    def reward_line(reward, ui_lang):
        actor = names["rewards"][reward]
        item = T.names(ui_lang)["item"].get(actor, reward)
        if reward in world.distribution.effective_starting_items and \
                world.distribution.effective_starting_items[reward].count > 0:
            where = T.names(ui_lang)["player"] + " (start)"
        else:
            loc = world.hinted_dungeon_reward_locations.get(reward)
            area = Hints.HintArea.at(loc) if loc is not None else Hints.HintArea.ROOT
            label = names["areas"].get(area.name)
            if s.clearer_hints and label:
                where = T.names(ui_lang)["location"].get(label, area.display_name(lang))
            else:
                where = area.text(lang, s.clearer_hints).replace("#", "")
                where = T.remake_names(where)
        return f"\x05{chr(0x40 + _colour_code(REWARD_COLORS.get(reward, 'Red')))}{item}\x05\x40: {where}"

    def text(ui_lang):
        pages = []
        if include_rewards:
            pages.append(T.mark(get_hint("Spiritual Stone Text Start", lang, s.clearer_hints).text))
            stones = ("Kokiri Emerald", "Goron Ruby", "Zora Sapphire")
            pages.append("\x01".join(reward_line(r, ui_lang) for r in stones))
        pages.append(dot_text(world))
        pages.append(T.mark(get_hint("Adult Altar Text Start", lang, s.clearer_hints).text))
        if include_rewards:
            meds = ("Light Medallion", "Forest Medallion", "Fire Medallion", "Water Medallion", "Shadow Medallion",
                    "Spirit Medallion")
            pages.append("\x01".join(reward_line(r, ui_lang) for r in meds[:3]))
            pages.append("\x01".join(reward_line(r, ui_lang) for r in meds[3:]))
        pages.append(bridge_text(world))
        pages.append(_period(O.unwrapped(Hints.build_ganon_boss_key_string, world)))
        return pages
    return _target_ops("altar", text)


def _period(control):
    """OoTR's Ganon's Boss Key line ends without a full stop ('...kept in a big chest inside its tower')."""
    plain = re.sub(r"\x05.", "", control).rstrip()
    return control + "." if plain and plain[-1] not in ".!?" else control


def _colour_code(name):
    codes = {"White": 0, "Red": 1, "Green": 2, "Blue": 3, "Light Blue": 4, "Pink": 5, "Yellow": 6, "Black": 7}
    return codes.get(name, 1)


def dot_text(world):
    """The Door of Time line. The remake's door follows the three child dungeons' boss defeats, not the stones
    (tools/rando/world_settings.py), so OoTR's 'Ye who owns 3 Spiritual Stones' is reworded for it."""
    import Hints
    if world.settings.open_door_of_time == "stones_oot_sot":
        return T.mark("Ye who has vanquished the evil within the #Great Deku Tree#, #Dodongo Cavern# and "
                      "#Lord Jabu-Jabu's Belly#... Stand with the #Ocarina of Time# and play the #Song of Time#.",
                      ["Light Blue"])
    return O.unwrapped(Hints.build_dot_reqs_string, world)


def bridge_text(world):
    """The rainbow bridge line. The remake's vanilla bridge appears after the Light Arrow cutscene, which follows
    the Shadow and Spirit Temple bosses (tools/rando/world_settings.py), so OoTR's vanilla wording ('collects the
    Shadow and Spirit Medallions as well as the Light Arrows') is reworded for it."""
    import Hints
    if world.settings.bridge == "vanilla":
        if world.settings.clearer_hints:
            return T.mark("The rainbow bridge will be built once the Hero has awakened the #Sages of Shadow and "
                          "Spirit# and met #Zelda in the Temple of Time#.", ["Green"])
        return T.mark("The awakened ones will await for the Hero to awaken the #Sages of Shadow and Spirit# and "
                      "meet #Zelda in the Temple of Time#.", ["Green"])
    return O.unwrapped(Hints.build_bridge_reqs_string, world)


def misc_item_ops(world):
    """Ganondorf (Light Arrows) and Dampe's diary (Hookshot): OoTR's build_misc_item_hints texts."""
    import Hints
    from HintList import misc_item_hint_table
    texts = O.capture(Hints.build_misc_item_hints, world, [])
    ops = []
    for hint_type, key in (("ganondorf", "ganondorf"), ("dampe_diary", "dampe_diary")):
        if hint_type in world.settings.misc_hints:
            text = texts.get(misc_item_hint_table[hint_type]["id"])
            if text:
                ops += _target_ops(key, lambda lang, t=text: t)
    return ops


def _location_item(world, hint_type):
    item = world.misc_hint_location_items.get(hint_type)
    if item is None:
        return None
    return O.item_text(O.generic_item_name(item), world)


def misc_location_ops(world):
    s = world.settings
    ops = []
    for hint_type, goal in SKULL_GOALS.items():
        item = _location_item(world, hint_type) if hint_type in s.misc_hints else None
        if item is None:
            continue
        if goal == 100:
            text = (f"If you collect a total of #{goal}# tokens, I believe you would at last free me from this "
                    f"ghastly curse... and you would receive #{item}#.")
        else:
            text = (f"If you collect a total of #{goal}# tokens, you would surely free one of my children from "
                    f"this curse... and you would receive #{item}#.")
        ops += _target_ops(hint_type, _english_marked(text, ["Red", "Green"]))
    item = _location_item(world, "frogs2") if "frogs2" in s.misc_hints else None
    if item:
        ops += _target_ops("frogs2", _english_marked(f"Once we're full, we'll give you #{item}#!", ["Green"]))
    item = _location_item(world, "big_poes") if "big_poes" in s.misc_hints else None
    if item:
        n = s.big_poe_count
        ops += _target_ops("big_poes", _english_marked(
            f"Bring me #{n} big poe{'s' if n != 1 else ''}#, and I'll give you #{item}#! Hehehe!", ["Red", "Green"]))
    pages = []
    for hint_type, mask in (("skull_mask", "Skull Mask"), ("mask_of_truth", "Mask of Truth")):
        item = _location_item(world, hint_type) if hint_type in s.misc_hints else None
        if item:
            pages.append(T.mark(f"Wearing the #{mask}# will reward you with #{item}#.", ["Red", "Green"]))
    if pages:
        ops += _target_ops("theater", lambda lang: list(pages))
    return ops


def _english_marked(text, colors):
    return lambda lang: T.mark(text, colors)


def merchant_ops(world):
    """The carpet merchant, the one unique merchant the shops plugin randomizes (with shuffle_expensive_merchants).
    unique_merchants names his item before the sale with OoTR's clear item name, like OoTR does. After the sale
    his line names the item he actually sold (vanilla says 'Bombchus')."""
    s = world.settings
    if not s.shuffle_expensive_merchants:
        return []
    try:
        loc = world.get_location("Wasteland Bombchu Salesman")
    except KeyError:
        return []
    if loc.item is None:
        return []
    item = O.item_text(O.generic_item_name(loc.item), world, clearer=True)
    ops = []
    if "unique_merchants" in s.misc_hints:
        spec = T.targets()["targets"]["carpet_salesman"]
        for m in [spec] + spec.get("also", []):
            ops += _message_ops(m["file"], m["label"], _english_marked(
                f"Today's special is... #{item}#! Scary! Ooo! Rare and not-usual, from all over the world!", ["Red"]),
                replace_pages=[1], note="unique_merchants")
    spec = T.targets()["targets"]["carpet_sold"]
    ops += _message_ops(spec["file"], spec["label"], _english_marked(
        f"It is a pleasure that we do business! And with the selling complete, you are of course seeing... the "
        f"answer... was #{item}#!", ["Red"]), replace_pages=[0], note="shuffle_expensive_merchants")
    return ops


def warp_ops(world):
    """Warp songs and owls whose destinations are shuffled (OoTR's update_warp_song_text). The remake's prompts
    name the destination when warp_songs_and_owls is on and say 'a mysterious place' otherwise."""
    from Hints import HintArea
    s = world.settings
    named = "warp_songs_and_owls" in s.misc_hints
    ops = []

    def dest(entrance_name):
        if not named:
            return "a mysterious place"
        region = world.get_entrance(entrance_name).connected_region
        area = HintArea.at(region)
        text = area.text(world.language, True).replace("#", "")
        return T.remake_names(text)
    if s.warp_songs:
        for ent, spec in T.targets()["warp_songs"].items():
            if ent.startswith("_"):
                continue
            d = dest(ent)
            ops += _message_ops("EventFlowMsg/Dm_SY_Ocarina.msbt", spec["confirm"],
                                _english_marked(f"Warp to #{d}#?", ["Red"]), note="warp_songs")
            ops += _message_ops("LayoutMsg/Ocarina_00.msbt", spec["caption"],
                                _english_marked(f"Play this tune to travel to {d}.", []), note="warp_songs",
                                width=70)  # the song list's caption is one line (vanilla up to 66 characters)
            ops += _message_ops("ActorMsg/PouchContent.msbt", spec["get_caption"],
                                _english_marked(f"Play this melody to warp to {d}.", []), note="warp_songs")
    if getattr(s, "owl_drops", False):
        for ent, specs in T.targets()["owls"].items():
            if ent.startswith("_"):
                continue
            d = dest(ent)
            for spec in specs:
                pages = [p.replace("{dest}", d) for p in spec["pages"]]
                ops += _message_ops(spec["file"], spec["label"],
                                    lambda lang, pages=pages: [T.mark(p, ["Red"]) for p in pages],
                                    keep_pages=spec.get("keep_pages", ()), note="owl_drops")
    return ops


def seed_info_ops(world):
    """show_seed_info / user_message. OoTR shows them on the file select screen. Here the first text box of a new
    file (Navi's first line in the opening) gets a page with them."""
    s = world.settings
    if not s.show_seed_info:
        return []
    from version import __version__
    lines = [f"OoT Randomizer {__version__.split()[0]}, seed {s.seed}."]
    spoiler = _spoiler_of(world)
    if spoiler is not None and getattr(spoiler, "file_hash", None):
        from Spoiler import HASH_ICONS
        lines.append("Hash: " + ", ".join(HASH_ICONS[i] for i in spoiler.file_hash) + ".")
    msg = (s.user_message or "").strip()[:42]
    if msg:
        lines.append("\x04" + msg)
    text = "\x01".join(lines).replace("#", "")
    return _target_ops("seed_info", lambda lang: text, note="show_seed_info")


def _spoiler_of(world):
    """The spoiler OoTR built for this world. It's world.spoiler if the generator sets it
    otherwise we find it among live objects.
    TODO: generate.py doesn't hand it to plugins today."""
    if getattr(world, "spoiler", None) is not None:
        return world.spoiler
    for o in gc.get_objects():
        if type(o).__name__ == "Spoiler" and world in getattr(o, "worlds", ()):
            return o
    return None


# Hints beyond OoTR (remake_extra_hints)
def _held(world, location):
    try:
        loc = world.get_location(location)
    except KeyError:
        return None
    return loc.item.name if loc.item is not None else None


def _first_location_of(world, item):
    """The first location (OoTR's order) holding `item`, or None (a starting item)."""
    for loc in world.get_locations():
        if loc.item is not None and loc.item.name == item and loc.type not in ("Event", "Hint", "HintStone"):
            return loc.name
    return None


def extra_ops(world, settings):
    """Text ops for remake_extra_hints (_hints_extra.py): frames per language with the game's own names."""
    from . import _hints_extra as X
    wanted = set(extra_hints(settings))
    if not wanted:
        return []
    ops = []

    def add(key, frames_for, only=None):
        for f, lb, mode in X.TARGETS[key]:
            if only is None or (f, lb) in only:
                ops.extend(X.message_ops(f, lb, mode, frames_for, f"{EXTRA_KEY} {key}"))

    def where(item):
        loc = _first_location_of(world, item)
        if loc is None:
            _pending["notes"].append(f"{EXTRA_KEY}: {item} is a starting item, no hint")
            return None
        return lambda lang: [X.where_text(X.item_name(item, lang), X.location_area(world, loc, lang), lang)]

    for key, item in (("mido", "Kokiri Sword"), ("saria", "Magic Meter")):
        f = where(item) if key in wanted else None
        if f:
            add(key, f)
    if "sheik" in wanted:
        gift, song = _held(world, "HF Ocarina of Time Item"), _held(world, "Song from Ocarina of Time")
        if gift and song:
            add("sheik", lambda lang: [X.reward_text("ocarina_gift", X.item_name(gift, lang), lang),
                                       X.reward_text("ocarina_song", X.item_name(song, lang), lang)])
    if "biggoron" in wanted:
        item = _held(world, "DMT Trade Claim Check")
        if item:
            add("biggoron", lambda lang: [X.reward_text(
                None, X.item_name(item, lang), lang, what=X._plain(T.names(lang)["item"].get("Item_ClaimCheck")))])
    for key, what, location in (("malon", "obstacle_course", "KF Links House Cow"),
                                ("anju", "cuccos", "Kak Anju as Child")):
        item = _held(world, location) if key in wanted else None
        if item:
            # The Anju hint writes Talk_21 and needs the current chicken count. _story_traps only writes Talk_21 when
            # this hint is off, and it still writes the other count lines.
            from . import _story_traps as TR
            n = TR.cucco_count(world.settings) if key == "anju" else 7
            add(key, lambda lang, what=what, item=item, n=n: [X.reward_text(
                what, X.item_name(item, lang), lang, what=TR.cucco_hint_what(lang, n) if n != 7 else None)])
    if "archery" in wanted:
        low, high = _held(world, "GF HBA 1000 Points"), _held(world, "GF HBA 1500 Points")
        if low and high:
            (f16, l16, _m), (f17, l17, _m2) = X.TARGETS["archery"]
            add("archery", lambda lang: [X.reward_text("points_750", X.item_name(low, lang), lang),
                                         X.reward_text("points_1400", X.item_name(high, lang), lang)],
                only={(f16, l16)})
            add("archery", lambda lang: [X.reward_text("points_1400", X.item_name(high, lang), lang)],
                only={(f17, l17)})
    if "fishing" in wanted:
        (fc, lc, _m), (fa, la, _m2) = X.TARGETS["fishing"]
        for (f, lb), location in (((fc, lc), "LH Child Fishing"), ((fa, la), "LH Adult Fishing")):
            item = _held(world, location)
            if item:
                add("fishing", lambda lang, item=item: [X.reward_text("fishing_prize", X.item_name(item, lang), lang)],
                    only={(f, lb)})
    if "merchants" in wanted:
        sellers = []
        if settings.shuffle_expensive_merchants:
            sellers += [("Npc_Goron_Medigoron_Adult", "GC Medigoron"),
                        ("Npc_Hylia_053_Adult", "Kak Granny Buy Blue Potion")]
        if getattr(settings, "shuffle_beans", False):
            sellers.append(("Npc_Hylia_047_Child", "ZR Magic Bean Salesman"))
        for npc, location in sellers:
            item = _held(world, location)
            if item:  # Granny's line is her offer itself (rewritten whole, with the price her sale takes)
                price = npc == "Npc_Hylia_053_Adult"
                add("merchants", lambda lang, item=item, price=price: [
                    X.special_text(X.item_name(item, lang), lang, price=price)],
                    only={(f, lb) for f, lb, _m in X.TARGETS["merchants"] if f.endswith(f"/{npc}.msbt")})
    ops += _misc_alias_ops(world, wanted)
    return ops


def _misc_alias_ops(world, wanted):
    """poe_collector / skulltula_100 / carpet_merchant turn on OoTR's own misc hints (in English, as OoTR writes
    them) when misc_hints doesn't already ask for them."""
    s = world.settings
    misc = set(s.misc_hints or [])
    ops = []

    def item_text(location):
        item = world.get_location(location).item
        return O.item_text(O.generic_item_name(item), world) if item is not None else None
    if "skulltula_100" in wanted and "100_skulltulas" not in misc:
        item = item_text("Kak 100 Gold Skulltula Reward")
        if item:
            text = (f"If you collect a total of #100# tokens, I believe you would at last free me from this "
                    f"ghastly curse... and you would receive #{item}#.")
            ops += _target_ops("100_skulltulas", _english_marked(text, ["Red", "Green"]))
    if "poe_collector" in wanted and "big_poes" not in misc:
        item = item_text("Market 10 Big Poes")
        if item:
            n = s.big_poe_count
            ops += _target_ops("big_poes", _english_marked(
                f"Bring me #{n} big poe{'s' if n != 1 else ''}#, and I'll give you #{item}#! Hehehe!",
                ["Red", "Green"]))
    if "carpet_merchant" in wanted and "unique_merchants" not in misc and s.shuffle_expensive_merchants:
        loc = world.get_location("Wasteland Bombchu Salesman")
        if loc.item is not None:
            item = O.item_text(O.generic_item_name(loc.item), world, clearer=True)
            spec = T.targets()["targets"]["carpet_salesman"]
            for m in [spec] + spec.get("also", []):
                ops += _message_ops(m["file"], m["label"], _english_marked(
                    f"Today's special is... #{item}#! Scary! Ooo! Rare and not-usual, from all over the world!",
                    ["Red"]), replace_pages=[1], note="carpet_merchant")
    return ops


# Plan
def world_plan(settings, world):
    from . import _hints_shuffle
    _pending["ops"], _pending["notes"] = [], []
    misc = set(settings.misc_hints or [])
    ops = []
    if "altar" in misc:
        ops += altar_ops(world)
    ops += misc_item_ops(world)
    ops += misc_location_ops(world)
    ops += merchant_ops(world)
    ops += warp_ops(world)
    ops += seed_info_ops(world)
    ops += extra_ops(world, settings)
    if settings.text_shuffle != "none":
        exempt = {(op["file"], op["label"]) for op in ops}
        ops = _hints_shuffle.shuffle_ops(settings.text_shuffle, exempt, settings.seed) + ops
    _pending["ops"] = ops
    out = {}
    if ops:
        out["text"] = ops
    if _pending["notes"]:
        out["_notes_hints"] = list(_pending["notes"])
    return out


# Gossip Stones
def gossip_text(gossip_stones, ops):
    """Gossip Stone text ops. Each stone's hint goes on its paired label (data/rando/hints_stones.json) with the
    remake's names, box size and colours (_hints_gossip). This is for a generator that offers the hook
    `ops` are generate.gossip_text_ops' ops (area-name
    pairing), and these replace them."""
    from . import _hints_gossip
    return _hints_gossip.gossip_ops(gossip_stones)


# Generate.py's text overwrite (workaround)
def _generator_modules():
    for name in ("__main__", "generate"):
        mod = sys.modules.get(name)
        if mod is not None and hasattr(mod, "gossip_text_ops") and hasattr(mod, "merge_plan"):
            yield mod


def _install_text_guard():
    """generate.py's main() sets plan["text"] = gossip_text_ops(...) after the plugins' world_plan parts are merged,
    which drops every plugin's text ops (the shops plugin's too) when hints are on.
    TODO: generate.py should append instead. Until then this
    wraps its merge_plan, which records the text ops merged, and gossip_text_ops, which returns those ops and then
    the Gossip Stone ops this plugin builds (each stone's hint on its real label, worded for the remake). It's for
    this run only. When main() already appends, only the Gossip Stone ops are replaced, and with a gossip_text hook
    nothing is."""
    import inspect
    for gen in _generator_modules():
        if getattr(gen, "_hints_text_guard", False):
            continue
        try:
            src = inspect.getsource(gen.main)
        except (OSError, TypeError, AttributeError):
            src = ""
        appends = 'plan.get("text", []) +' in src or "plan['text'] +" in src or 'plan["text"] +' in src
        if ".gossip_text(" in src:
            gen._hints_text_guard = True
            continue
        recorded = []
        orig_merge, orig_gossip = gen.merge_plan, gen.gossip_text_ops

        def merge_plan(plan, part, _orig=orig_merge, _rec=recorded):
            _rec.extend(part.get("text", []) or [])
            return _orig(plan, part)

        def gossip_text_ops(gossip_stones, _orig=orig_gossip, _rec=recorded, _appends=appends):
            from . import _hints_gossip  # the exact stone labels, from hints_stones.json
            ops = _hints_gossip.gossip_ops(gossip_stones)
            return ops if _appends else list(_rec) + ops
        if not appends:
            gen.merge_plan = merge_plan
        gen.gossip_text_ops = gossip_text_ops
        gen._hints_text_guard = True
