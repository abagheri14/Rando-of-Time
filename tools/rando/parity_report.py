"""Write PARITY.md: every OoT Randomizer setting, its plugin, and what the remake randomizer supports today.

usage: python tools/rando/parity_report.py

Statuses come from the code, so the report can't drift. They're settings a parity plugin owns
(tools/rando/parity/*.py OWNS), settings tools/rando/world_settings.py applies (APPLIED) or pins to the remake's
own behaviour (REMAKE_ONLY), and the generator's own support (CORE below). "not seen in-game" marks values the
patcher applies that haven't been checked in a play test yet (a plugin lists settings seen working in-game in
VERIFIED).
"""
import contextlib
import importlib
import io
import os
import pkgutil
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(HERE, "vendor", "ootr"))
sys.path.insert(0, os.path.join(HERE, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
with contextlib.redirect_stdout(io.StringIO()):
    from SettingsList import SettingInfos  # noqa: E402
import world_settings  # noqa: E402

PLUGIN_AREAS = [
    ("core", "Core: generator, patcher, hints, starting items",
     "show_seed_info user_message world_count create_spoiler password_lock randomize_settings logic_rules "
     "reachable_locations disabled_locations allowed_tricks advanced_allowed_tricks starting_items "
     "starting_equipment starting_inventory starting_songs add_random_starting_items random_starting_items_exclude "
     "random_starting_items_count start_with_consumables start_with_rupees starting_hearts clearer_hints hints "
     "hint_dist item_hints hint_dist_user misc_hints plandomized_locations item_pool_value one_item_per_dungeon "
     "shuffle_kokiri_sword shuffle_ocarinas shuffle_dungeon_rewards text_shuffle"),
    ("dungeons", "Dungeons and keys",
     "mq_dungeons_mode mq_dungeons_specific mq_dungeons_count empty_dungeons_mode empty_dungeons_specific "
     "empty_dungeons_rewards empty_dungeons_count dungeon_shortcuts_choice dungeon_shortcuts shuffle_map "
     "shuffle_compass enhance_map_compass shuffle_smallkeys shuffle_hideoutkeys key_rings_choice key_rings "
     "keyring_give_bk shuffle_bosskeys shuffle_ganon_bosskey ganon_bosskey_medallions ganon_bosskey_stones "
     "ganon_bosskey_rewards ganon_bosskey_tokens ganon_bosskey_hearts shuffle_silver_rupees "
     "silver_rupee_pouches_choice silver_rupee_pouches key_appearance_match_dungeon trials_random trials"),
    ("entrances", "Entrance randomizer",
     "shuffle_interior_entrances shuffle_hideout_entrances shuffle_grotto_entrances shuffle_dungeon_entrances "
     "shuffle_bosses shuffle_ganon_tower shuffle_overworld_entrances shuffle_gerudo_valley_river_exit owl_drops "
     "warp_songs spawn_positions starting_age"),
    ("story", "Story and quality-of-life settings",
     "triforce_hunt triforce_count_per_world triforce_goal_per_world lacs_condition lacs_medallions lacs_stones "
     "lacs_rewards lacs_tokens lacs_hearts bridge bridge_medallions bridge_stones bridge_rewards bridge_tokens "
     "bridge_hearts open_forest open_kakariko open_door_of_time zora_fountain gerudo_fortress skip_reward_from_rauru "
     "no_escape_sequence no_guard_stealth no_epona_race skip_some_minigame_phases complete_mask_quest "
     "useful_cutscenes fast_chests scarecrow_behavior fast_bunny_hood auto_equip_masks plant_beans "
     "easier_fire_arrow_entry fae_torch_count ruto_already_f1_jabu fast_shadow_boat chicken_count_random "
     "chicken_count big_poe_count_random big_poe_count damage_multiplier deadly_bonks starting_tod blue_fire_arrows "
     "logic_no_night_tokens_without_suns_song"),
    ("chests", "Ice traps, chests, Treasure Chest Game",
     "junk_ice_traps custom_ice_trap_percent custom_ice_trap_count ice_trap_appearance correct_chest_appearances "
     "chest_textures_specific soa_unlocks_chest_texture minor_items_as_major_chest invisible_chests shuffle_tcgkeys "
     "tcg_requires_lens"),
    ("songs_trade", "Songs, trade sequences, cows and other special items",
     "shuffle_song_items shuffle_child_trade adult_trade_shuffle adult_trade_start shuffle_cows shuffle_gerudo_card "
     "shuffle_frog_song_rupees shuffle_100_skulltula_rupee shuffle_loach_reward shuffle_individual_ocarina_notes "
     "ocarina_songs free_bombchu_drops shuffle_gerudo_fortress_heart_piece"),
    ("drops", "Drops: Gold Skulltulas, freestanding items, pots, crates, beehives",
     "tokensanity shuffle_freestanding_items shuffle_pots shuffle_empty_pots shuffle_crates shuffle_empty_crates "
     "shuffle_beehives shuffle_wonderitems correct_potcrate_appearances potcrate_textures_specific "
     "soa_unlocks_potcrate_texture no_collectible_hearts fix_broken_drops gold_skulls_ignore_daytime"),
    ("shops", "Shops, scrubs, merchants",
     "shopsanity special_deal_price_distribution special_deal_price_min special_deal_price_max shuffle_scrubs "
     "shuffle_expensive_merchants shuffle_beans"),
]
# What the generator itself handles (OoTR's own fill, pool, hints and spoiler).
CORE = {
    "create_spoiler": "all", "logic_rules": "glitchless, none (No Logic: seeds generate and patch); remake_glitched and advanced (loaded as remake_glitched) need the glitches plugin", "reachable_locations": "all",
    "disabled_locations": "all", "item_pool_value": "all (OoTR's pool)", "one_item_per_dungeon": "all (OoTR's fill)",
    "hint_dist": "all (OoTR's)", "hints": "none, mask, agony, always (Gossip Stone text; agony not seen in-game)",
    "add_random_starting_items": "all (opening scene), not seen in-game", "random_starting_items_count": "all",
    "random_starting_items_exclude": "all", "start_with_consumables": "true/false (opening scene), not seen in-game",
    "randomize_settings": "all (OoTR's; the result must be supported)", "plandomized_locations": "all (OoTR's plando)",
    "shuffle_kokiri_sword": "all", "shuffle_ocarinas": "all", "shuffle_dungeon_rewards": "all (boss rewards are scene locations)",
    "starting_items": "all with a remake item (opening scene), not seen in-game", "starting_equipment": "as starting_items",
    "starting_inventory": "as starting_items", "starting_songs": "as starting_items",
    "allowed_tricks": "off by default; tricks are verified one by one (tools/trick_checklist.py)",
    "world_count": "1 only: multiworld needs items sent between games while playing (Longshot loads files only)",
}


def plugin_owns():
    """Settings owned by the enabled plugins (config/plugins.json). Plugins still being built don't count."""
    import json
    enabled = json.load(open(os.path.join(HERE, "config", "plugins.json"), encoding="utf-8"))["enabled"]
    pkg = os.path.join(os.path.dirname(os.path.abspath(__file__)), "parity")
    owns, verified = {}, set()
    for m in pkgutil.iter_modules([pkg]):
        if m.name.startswith("_") or m.name not in enabled:
            continue
        mod = importlib.import_module(f"parity.{m.name}")
        for k, v in getattr(mod, "OWNS", {}).items():
            owns[k] = (m.name, v)
        verified |= set(getattr(mod, "VERIFIED", ()))
        NOTES.update(getattr(mod, "PARITY_NOTE", {}))
    return owns, verified


NOTES = {}  # a plugin's PARITY_NOTE: what its setting's row adds (e.g. an OoTR value that loads as another)


def status(name, owns, verified):
    def fmt(vals):
        return ", ".join(map(str, vals))
    if name in owns:
        mod, vals = owns[name]
        tag = "" if name in verified else " (not seen in-game)"
        note = f"; {NOTES[name]}" if name in NOTES else ""
        return f"{fmt(vals) if vals is not None else 'checked by plugin'} [{mod}]{tag}{note}"
    if name in world_settings.APPLIED:
        vals = world_settings.APPLIED[name]
        shown = f"{min(vals)}-{max(vals)}" if all(isinstance(v, int) and not isinstance(v, bool) for v in vals) \
            else fmt(vals)
        return f"{shown} [world_settings] (new values not seen in-game)"
    if name in world_settings.SUPPORTED:
        return ", ".join(map(repr, world_settings.SUPPORTED[name])) + " [generator]"
    if name in world_settings.REMAKE_ONLY:
        return f"only {world_settings.REMAKE_ONLY[name]!r} (the remake's own behaviour)"
    if name in CORE:
        return CORE[name]
    if name in world_settings.GENERATOR_ANY:
        return "all [generator]"
    return "OoTR's default only (refused otherwise)"


def _short(name, owns, info):
    """Whether the remake supports fewer values of this setting than OoTR offers."""
    choices = getattr(info, "choices", None)
    if name in owns:
        vals = owns[name][1]
    elif name in world_settings.APPLIED:
        vals = world_settings.APPLIED[name]
    elif name in world_settings.SUPPORTED:
        vals = world_settings.SUPPORTED[name]
    elif name in world_settings.REMAKE_ONLY:
        vals = (world_settings.REMAKE_ONLY[name],)
    elif name in world_settings.GENERATOR_ANY or name in CORE:
        return False
    else:
        vals = (info.default,)
    if vals is None:
        return False
    if isinstance(choices, dict) and len(choices) > 1:
        return len(set(map(str, vals)) & set(map(str, choices))) < len(choices)
    return type(info).__name__ == "Checkbutton" and len(vals) < 2


def remake_section():
    """The remake's own settings (features OoTR doesn't have) by plugin, with choices, default, and the familiar names
    a settings file may use instead (config/setting_aliases.json, Ship of Harkinian's or OoTR-style)."""
    import json
    table = json.load(open(os.path.join(HERE, "config", "setting_aliases.json"), encoding="utf-8"))
    names = {}
    for alias, a in table["names"].items():
        names.setdefault(a["key"], []).append((alias, a))
    out = ["## Remake settings (features OoTR doesn't have)", "",
           "These keys all start with `remake_`. A settings file can also use the familiar name from the second column, "
           "with the",
           "values shown there. That's the Ship of Harkinian setting, or an OoTR-style name for a feature OoTR doesn't "
           "have.", "",
           "| Setting | Familiar name (values) | Choices | Default | Plugin |", "|---|---|---|---|---|"]
    with contextlib.redirect_stdout(io.StringIO()):
        importlib.import_module("generate").ootr()
    for name in sorted(m.name for m in pkgutil.iter_modules([os.path.join(HERE, "tools", "rando", "parity")])
                       if not m.name.startswith("_")):
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                mod = importlib.import_module(f"parity.{name}")
        except Exception:  # noqa: BLE001 - a plugin that can't load lists nothing here
            continue
        rs, d = getattr(mod, "REMAKE_SETTINGS", None) or {}, getattr(mod, "REMAKE_DEFAULTS", None) or {}
        for k, ch in rs.items():
            fam = "; ".join(f"`{al}`" + (f" ({', '.join(a['values'])})" if a.get("values") else "")
                            + (f" from {a['source']}" if a.get("source") else "") for al, a in names.get(k, []))
            choices = ", ".join(map(str, ch)) if isinstance(ch, (tuple, list)) else "see plugin"
            dflt = d.get(k) if d.get(k) is not None else (
                "off" if isinstance(ch, (tuple, list)) and "off" in ch else "see the plugin")
            out.append(f"| `{k}` | {fam} | {choices} | {dflt} | {name} |")
    return out + [""]


def main():
    owns, verified = plugin_owns()
    infos = SettingInfos.setting_infos
    assigned = {}
    for ws, title, names in PLUGIN_AREAS:
        for n in names.split():
            assigned[n] = ws
    out = ["# OoT Randomizer parity", "",
           "The goal is that every OoT Randomizer setting and location type works in the remake. The one exception is "
           "glitch",
           "logic, because the remake's geometry is different. Tricks stay off by default and I verify them one by one. "
           "This file",
           "is generated by `tools/rando/parity_report.py` from OoTR's SettingsList and the code, so don't edit it by "
           "hand.", ""]
    todo = 0
    import json
    familiar = {}  # OoTR settings that also take a Ship of Harkinian name (config/setting_aliases.json)
    for al, a in json.load(open(os.path.join(HERE, "config", "setting_aliases.json"), encoding="utf-8"))["names"].items():
        if not a["key"].startswith("remake_"):
            familiar.setdefault(a["key"], []).append(al)
    for ws, title, _ in PLUGIN_AREAS + [("cosmetics", "Cosmetics", "")]:
        names = ([n for n, s in infos.items() if s.cosmetic] if ws == "cosmetics"
                 else [n for n, s in infos.items() if s.shared and assigned.get(n) == ws])
        out += [f"## {title}", "", "| Setting | OoTR choices | Remake |", "|---|---|---|"]
        for n in names:
            ch = getattr(infos[n], "choices", None)
            ch = (", ".join(map(str, list(ch)[:8])) + (" ..." if len(ch) > 8 else "")) if isinstance(ch, dict) else ""
            st = status(n, owns, verified)
            if n in familiar:
                st += "; also as " + ", ".join(f"`{al}` (Ship of Harkinian)" for al in familiar[n])
            todo += _short(n, owns, infos[n])
            out.append(f"| `{n}` | {ch} | {st} |")
        out.append("")
    out += remake_section()
    missing = [n for n, s in infos.items() if s.shared and n not in assigned]
    out += ["## Not seed settings", "",
            "OoTR's output and GUI options (ROM files, patch files, GUI state) don't mean anything in the remake.", ""]
    if missing:
        out += ["Unassigned seed settings: " + ", ".join(missing), ""]
    open(os.path.join(HERE, "PARITY.md"), "w", encoding="utf-8").write("\n".join(out) + "\n")
    print(f"PARITY.md: {todo} settings support fewer values than OoTR offers")


if __name__ == "__main__":
    main()
