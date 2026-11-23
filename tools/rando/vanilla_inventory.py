"""List every OoT Randomizer location the code still locks to its vanilla item.

My rule: nothing stays vanilla unless a setting says so. This turns on every location shuffle OoTR has
(tokens, freestanding, pots, crates, beehives, wonder items, cows, beans, merchants, frogs, shops, scrubs, keys,
silver rupees, maps/compasses, songs anywhere), builds the world with the enabled plugins and lists the locations
no plugin keeps (tools/rando/generate.py lock_unpatchable would lock them). The goal is an empty list, apart from
OoTR locations proven absent from the remake (those belong in OoTR's disabled/removed set, with evidence).

usage: python tools/rando/vanilla_inventory.py [OUT.json] [--type Pot,Crate]
"""
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import generate as G  # noqa: E402

ALL_ON = dict(tokensanity="all", shuffle_scrubs="low", shuffle_freestanding_items="all", shuffle_pots="all",
              shuffle_crates="all", shuffle_cows=True, shuffle_beehives=True, shuffle_wonderitems=True,
              shuffle_gerudo_card=True, shuffle_beans=True, shuffle_expensive_merchants=True,
              shuffle_frog_song_rupees=True, shopsanity="4", shuffle_smallkeys="keysanity",
              shuffle_bosskeys="keysanity", shuffle_hideoutkeys="keysanity", shuffle_tcgkeys="keysanity",
              shuffle_silver_rupees="anywhere", shuffle_ganon_bosskey="keysanity", shuffle_map="keysanity",
              shuffle_compass="keysanity", shuffle_song_items="any", shuffle_loach_reward="vanilla",
              shuffle_100_skulltula_rupee=True, shuffle_gerudo_fortress_heart_piece="shuffle",
              shuffle_empty_pots=True, shuffle_empty_crates=True,
              # the remake's own object shuffles (tools/rando/parity/drops.py)
              remake_shuffle_grass="all", remake_shuffle_rocks="all", remake_shuffle_boulders="all",
              remake_shuffle_misc="all", adult_trade_shuffle=True,
              shuffle_child_trade=["Weird Egg", "Chicken", "Zeldas Letter", "Keaton Mask", "Skull Mask", "Spooky Mask",
                                   "Bunny Hood", "Goron Mask", "Zora Mask", "Gerudo Mask", "Mask of Truth"],
              complete_mask_quest=True)


def inventory():
    Main, Goals, ShuffleError, ItemFactory, Settings, SettingInfos = G.ootr()
    cfg = G.load_settings(os.path.join(G.HERE, "config", "rando_settings.json"))
    cfg.update(ALL_ON)
    chest_map = json.load(open(os.path.join(G.HERE, "data", "rando", "chest_map.json"), encoding="utf-8"))["chests"]
    keep = {n for n, v in chest_map.items() if v["mode"] in ("full", "group")} | set(G.scene_locations())
    settings = G.make_settings(Settings, cfg, 1, [], None)
    Main.resolve_settings(settings)
    mods = G.plugins()
    G.world_settings.install_logic(enabled=set(G.enabled_plugins()), plugins=set(G.all_plugins()))
    for m in mods:
        if hasattr(m, "before_build"):
            m.before_build(settings)
    world = Main.build_world_graphs(settings)[0]
    for m in mods:
        if hasattr(m, "keep_locations"):
            keep |= set(m.keep_locations(world, settings))
    out = collections.defaultdict(list)
    for loc in world.get_locations():
        if loc.type in G.NOT_ITEM_CHECKS or loc.name in keep:
            continue
        if loc.item is not None and loc.locked:  # OoTR prefilled it itself (like Gift from Sages with Nothing)
            continue
        out[loc.type].append({"name": loc.name, "vanilla": loc.vanilla_item,
                              "disabled": loc.name in settings.disabled_locations})
    return {t: sorted(v, key=lambda x: x["name"]) for t, v in out.items()}, len(keep)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    types = None
    if "--type" in sys.argv:
        types = set(sys.argv[sys.argv.index("--type") + 1].split(","))
        args = [a for a in args if a != sys.argv[sys.argv.index("--type") + 1]]
    out, kept = inventory()
    if types:
        out = {t: v for t, v in out.items() if t in types}
    print(f"kept (patchable): {kept}; still locked vanilla: {sum(len(v) for v in out.values())}")
    for t, v in sorted(out.items(), key=lambda kv: -len(kv[1])):
        print(f"== {t}: {len(v)}")
        for x in v:
            print(f"   {x['name']} | {x['vanilla']}{' | disabled' if x['disabled'] else ''}")
    if args:
        json.dump(out, open(args[0], "w", encoding="utf-8"), indent=1)


if __name__ == "__main__":
    if os.environ.get("PYTHONHASHSEED") != "0":
        os.environ["PYTHONHASHSEED"] = "0"
        os.execv(sys.executable, [sys.executable] + sys.argv)
    main()
