"""How the randomizer app shows the remake's own settings (the plugins' REMAKE_SETTINGS and REMAKE_KEYS): where
they go, their label, explanation and value names. tools/release/export_schema.py reads this. A remake setting
missing here still shows up, in the remake-only section with its raw name, and the export names it so it gets a
line here.

Each setting goes in the OoTR tab and section where OoTR or Ship of Harkinian puts the same kind of setting (for SoH
that's settings.cpp's menus). It sits right after the OoTR setting it's listed with,
the anchor, which is the first field of its line. Several after one anchor show in this file's order. If the export
doesn't offer the anchor, the setting goes at the end of that anchor's OoTR section, and an anchor written as
"tab/section" means the end of that section.
Labels follow OoTR's style (title case, "Shuffle X" for a shuffle) since they sit among OoTR's own.
"""

LEVELS = {"off": "Off", "dungeons": "Dungeons only", "overworld": "Overworld only", "all": "Everywhere"}

# Settings with no OoTR or Ship of Harkinian counterpart show here, at the end of OoTR's "Other" tab. That's only
# remake_racing and any remake setting without a line in UI below. remake_racing is OoT3D Randomizer's Racing, and it
# locks options from several tabs (cosmetics, sounds and timesavers), so no single OoTR section owns it.
REMAKE_HOME = "other_tab/remake_section"
SECTION_TEXT = {"remake_section": "Remake Only"}

PRICE_MODES = {"ootr": "OoTR's prices", "vanilla": "Vanilla", "cheap_balanced": "Cheap (0-95)",
               "balanced": "Balanced (0-295)", "fixed": "Fixed", "range": "Range", "wallet": "By wallet weights",
               "affordable": "10 rupees each", "child_wallet": "Up to 99", "adult_wallet": "Up to 200",
               "giant_wallet": "Up to 500"}


def _prices(kind, what, anchor):
    """A price mode and its numbers (parity/extras_prices.py), placed right after the OoTR shuffle they price. Ship of
    Harkinian lists its shop, scrub and merchant prices after each shuffle the same way."""
    out = {f"remake_{kind}_prices": (
        anchor, f"{what}: Prices", PRICE_MODES,
        "Ship of Harkinian's and OoT3D Randomizer's price modes. Balanced and the \"up to\" modes favour cheap "
        "prices; by wallet weights draws how often a price needs no wallet, the child's, the adult's or the "
        "giant's wallet. Every price is 0-500.")}
    out[f"remake_{kind}_price_fixed"] = (anchor, f"{what}: Fixed Price", None, "Rupees, 0-500 (mode Fixed).")
    out[f"remake_{kind}_price_range_1"] = (anchor, f"{what}: Range From", None, "Rupees, 0-500 (mode Range).")
    out[f"remake_{kind}_price_range_2"] = (anchor, f"{what}: Range To", None, "Rupees, 0-500 (mode Range).")
    for w, label in (("none", "Free"), ("child", "Child's Wallet"), ("adult", "Adult's Wallet"),
                     ("giant", "Giant's Wallet")):
        out[f"remake_{kind}_price_weight_{w}"] = (anchor, f"{what}: Weight, {label}", None,
                                                  "0-100 (mode By wallet weights).")
    out[f"remake_{kind}_prices_affordable"] = (
        anchor, f"{what}: Affordable", None,
        "Each price drops to the cheapest of its wallet tier: 5, 100 or 205 rupees (Ship of Harkinian; not with "
        "a fixed price).")
    return out


UI = {
    # Main Rules > Open (SoH: Area Access)
    "remake_sleeping_waterfall": ("zora_fountain", "Zora's River Waterfall",
                                  {"closed": "Needs Zelda's Lullaby", "open": "Open"},
                                  "'Open': the waterfall to Zora's Domain is parted from the start, so getting in "
                                  "needs no Zelda's Lullaby (Ship of Harkinian's Sleeping Waterfall)."),
    "remake_jabu_mouth": ("zora_fountain", "Jabu-Jabu's Mouth", {"closed": "Needs a fish", "open": "Open"},
                          "Ship of Harkinian's / OoT3D Randomizer's open Jabu."),
    "remake_medallion_trials": ("trials", "Medallion-Locked Trials", None,
                                "Each trial's barrier room opens only with its medallion (Ship of Harkinian)."),
    # Main Rules > World (OoT3D Randomizer: World)
    "remake_enemizer": ("spawn_positions", "Enemy Randomizer", {"off": "Off", "on": "On"},
                        "Enemies swap with others their area already has, only where the logic still holds."),
    "remake_enemizer_vanilla": ("spawn_positions", "Enemies the Randomizer Leaves Alone", None,
                                "These enemies stay where they are and replace no other enemy (OoT3D Randomizer's "
                                "enemy list, \"Vanilla\")."),
    # Main Rules > Shuffle (SoH: Shuffle Items,
    # Shuffle Shops & Merchants, Additional Items)
    "remake_vanilla_songs": ("shuffle_song_items", "Songs Stay Vanilla", None,
                             "Every song is taught where the vanilla game teaches it (Ship of Harkinian's Shuffle "
                             "Songs: Off). Needs songs on song locations."),
    **_prices("shop", "Shop Special Deals", "special_deal_price_max"),
    "remake_shop_shields_tunics_after_found": ("special_deal_price_max",
                                               "Shops Sell Shields and Tunics Only Once Found", None,
                                               "Shields and tunics appear in shops only after you've found one "
                                               "(Ship of Harkinian)."),
    "remake_split_potion_shops": ("special_deal_price_max", "Shuffle Both Potion Shops", None,
                                  "The Market's and Kakariko's potion shops each get their own shuffled shelves."),
    "remake_gs_positions": ("tokensanity", "Gold Skulltula Positions",
                            {"off": "Vanilla", "on": "Random", "new": "Random, never their own spot"},
                            "Gold Skulltulas that can move take another spot of their area (OoT3D Randomizer)."),
    **_prices("scrub", "Business Scrubs", "shuffle_scrubs"),
    # which freestanding items OoTR's "Shuffle Rupees & Hearts" takes in
    "remake_vanilla_freestanding_rupees": ("shuffle_freestanding_items", "Freestanding Rupees Stay Vanilla", None,
                                           "With freestanding items shuffled, the rupees lying around stay rupees "
                                           "(OoT3D Randomizer's Shuffle Standing Rupees: Off)."),
    "remake_vanilla_freestanding_hearts": ("shuffle_freestanding_items", "Recovery Hearts Stay Vanilla", None,
                                           "With freestanding items shuffled, the recovery hearts lying around stay "
                                           "hearts (OoT3D Randomizer's Shuffle Recovery Hearts: Off)."),
    "remake_touch_pickups": ("shuffle_freestanding_items", "Auto-Collected Rupees and Hearts",
                             {"any": "Hold any item", "own_kind": "Stay what they are"},
                             "Rupees and hearts collected by touch (Zora's Fountain, Dampe's race...) can hold any "
                             "item."),
    "remake_freestanding_keys": ("shuffle_freestanding_items", "Bottom of the Well and Shadow Temple Floor Keys",
                                 {"any": "Hold any item", "vanilla": "Stay keys"},
                                 "The small keys lying on the floor in the Bottom of the Well and the Shadow Temple. "
                                 "'Hold any item': each gives the seed's item when picked up; 'Stay keys': they stay "
                                 "their dungeon's keys."),
    "remake_gc_pot_prize": ("shuffle_freestanding_items", "Goron City Spinning Pot Prize",
                            {"any": "Any item", "vanilla": "Its heart piece"},
                            "The prize of Goron City's big spinning pot (OoTR's GC Pot Freestanding PoH). 'Any "
                            "item': it gives the seed's item, held up; 'Its heart piece': it stays the heart piece."),
    "remake_zd_grotto_rupees": ("shuffle_freestanding_items", "Zora's Domain Grotto Rupees",
                                {"gift": "Hold items", "vanilla": "Stay rupees"},
                                "The six blue rupees in the Zora's Domain Song of Storms grotto."),
    # OoTR's pots and crates
    "remake_reset_group_objects": ("shuffle_empty_crates", "Pots That Refill with the Room",
                                   {"one_time": "Hold any item (recommended)", "respawn": "Hold junk only"},
                                   "Pots and crates the game refills together (dungeons, Kakariko, the Market). "
                                   "\"Hold any item\" lets them hold anything, as OoTR's pot checks; \"Hold junk "
                                   "only\" keeps the game's refills and gives them junk."),
    "remake_empty_object_contents": ("shuffle_empty_crates", "Empty Pots and Crates Give",
                                     {"vanilla": "Their own drop", "nothing": "Nothing", "junk": "A few rupees",
                                      "ice_trap": "An ice trap"},
                                     "What a shuffled pot or crate that OoTR leaves empty (\"Nothing\") gives."),
    # after OoTR's cows and beehives come the other objects that hold items, in Ship of Harkinian's order
    "remake_shuffle_grass": ("shuffle_beehives", "Shuffle Grass", LEVELS,
                             "Grass tufts and bushes hold items (Ship of Harkinian's Shuffle Grass). A tuft keeps "
                             "growing back with its item until you take it; after that it's normal grass."),
    "remake_shuffle_rocks": ("shuffle_beehives", "Shuffle Small Rocks", LEVELS,
                             "Small rocks you can lift hold items (Ship of Harkinian's Shuffle Rocks)."),
    "remake_shuffle_boulders": ("shuffle_beehives", "Shuffle Boulders and Silver Rocks", LEVELS,
                                "Bomb boulders, bronze (hammer) boulders and silver rocks hold items. They never come "
                                "back in vanilla: one whose item you left behind is back on your next visit with it."),
    "remake_shuffle_bushes": ("shuffle_beehives", "Shuffle Bushes", None,
                              "The 13 bushes in Hyrule Field hold items (Ship of Harkinian's Shuffle Bushes). Cut one "
                              "with a sword, the Boomerang or the hammer; after its item is taken it's a normal bush."),
    "remake_shuffle_trees": ("shuffle_beehives", "Shuffle Trees", LEVELS,
                             "Rolling into a tree drops an item (Ship of Harkinian's Shuffle Trees)."),
    "remake_shuffle_icicles": ("shuffle_beehives", "Shuffle Icicles", LEVELS,
                               "Falling icicles hold items (Ship of Harkinian's Shuffle Icicles)."),
    "remake_shuffle_red_ice": ("shuffle_beehives", "Shuffle Red Ice", LEVELS,
                               "Red ice melted with blue fire holds items (Ship of Harkinian's Shuffle Red Ice)."),
    "remake_shuffle_misc": ("shuffle_beehives", "Shuffle Palm Fruit and Decorations", LEVELS,
                            "Gerudo Valley palm fruit, cow skulls and sign decorations hold items."),
    "remake_shuffle_signs": ("shuffle_beehives", "Shuffle Signs", LEVELS,
                             "Reading a sign, tablet or grave the first time gives an item (Ship of Harkinian's "
                             "Shuffle Signs: 35 spots)."),
    "remake_drop_contents": ("shuffle_beehives", "What Shuffled Objects May Hold",
                             {"all": "Anything (recommended)", "safe": "Junk and harmless items", "junk": "Junk only"},
                             "\"Anything\" is OoTR's and Ship of Harkinian's: an object comes back with its item "
                             "until you take it."),
    "remake_shuffle_stone_fairies": ("shuffle_beehives", "Shuffle Gossip Stone Fairies", None,
                                     "Playing a song for a Gossip Stone gives an item along with its fairy: one for "
                                     "Zelda's Lullaby, Epona's Song, the Sun's Song or the Song of Time, another for "
                                     "the Song of Storms (Ship of Harkinian's Shuffle Stone Fairies: 80 checks)."),
    "remake_shuffle_fountain_fairies": ("shuffle_beehives", "Shuffle Fairy Fountains", None,
                                        "The Desert Colossus oasis, the Hyrule Field, Sacred Forest Meadow and Zora's "
                                        "River fairy grottos and the Graveyard's fairy grave give items: the oasis "
                                        "after its Song of Storms scene, a grotto or the grave the first time you "
                                        "drop in (Ship of Harkinian's Shuffle Fountain Fairies: 39 checks)."),
    "remake_shuffle_bean_fairies": ("shuffle_beehives", "Shuffle Bean Plant Fairies", None,
                                    "Playing the Song of Storms over a planted bean (as a child) gives three items "
                                    "along with its fairy (Ship of Harkinian's Shuffle Bean Fairies: 30 checks)."),
    "remake_shuffle_song_fairies": ("shuffle_beehives", "Shuffle Fairy Note Spots", None,
                                    "Playing the Sun's Song or the Song of Storms at a Fairy Note gives an item "
                                    "along with its fairy (Ship of Harkinian's Shuffle Song Fairies: 9 checks)."),
    "remake_shuffle_butterfly_fairies": ("shuffle_beehives", "Shuffle Butterfly Fairies", None,
                                         "The butterflies that turn into a fairy at a child's Deku Stick drop an item "
                                         "instead (Ship of Harkinian's Shuffle Butterfly Fairies: 15 checks)."),
    "remake_shuffle_big_poes": ("shuffle_beehives", "Shuffle Big Poes", None,
                                "Each of Hyrule Field's ten Big Poes gives an item when its soul is bottled (OoT3D "
                                "Randomizer)."),
    "remake_shuffle_fire_gorons": ("shuffle_beehives", "Shuffle Fire Temple Gorons", None,
                                   "Each freed Goron in the Fire Temple gives an item after his thank-you (Ship of "
                                   "Harkinian)."),
    "remake_wonderitems_area": ("shuffle_wonderitems", "Wonderitems Shuffled In",
                                {"all": "Everywhere", "dungeons": "Dungeons only", "overworld": "Overworld only"},
                                "Ship of Harkinian's Shuffle Wonder Items: where wonderitems hold seed items. The "
                                "remake has no wonderitems, so this changes nothing."),
    # equipment and item shuffles (SoH: Shuffle Items, Additional Items)
    "remake_shuffle_master_sword": ("shuffle_kokiri_sword", "Shuffle the Master Sword", None,
                                    "The Master Sword is an item somewhere in the world: pulling it from the pedestal "
                                    "needs it."),
    "remake_progressive_swords": ("shuffle_kokiri_sword", "Progressive Swords", None,
                                  "Kokiri Sword, Master Sword, Giant's Knife, Biggoron Sword in that order. Needs the "
                                  "Master Sword shuffled."),
    "remake_progressive_goron_sword": ("shuffle_kokiri_sword", "Progressive Goron Sword", None,
                                       "Giant's Knife then Biggoron Sword (Ship of Harkinian / OoT3D Randomizer)."),
    "remake_shuffle_deku_stick_bag": ("shuffle_gerudo_card", "Shuffle the Deku Stick Bag", None,
                                      "You can't carry Deku Sticks until you find the bag (Ship of Harkinian)."),
    "remake_shuffle_deku_nut_bag": ("shuffle_gerudo_card", "Shuffle the Deku Nut Bag", None,
                                    "You can't carry Deku Nuts until you find the bag (Ship of Harkinian)."),
    "remake_shuffle_child_wallet": ("shuffle_gerudo_card", "Shuffle the Child's Wallet", None,
                                    "You can't carry rupees until you find the first wallet (Ship of Harkinian)."),
    "remake_ammo_without_container": ("shuffle_gerudo_card", "Ammo Without Its Bag",
                                      {"blue_rupee": "Blue Rupee (OoTR)", "nothing": "Nothing (0/0)"},
                                      "Bombs, arrows or Deku Seeds you get before their bag, quiver or seed bag. OoTR "
                                      "gives a Blue Rupee instead. Nothing adds no ammo and shows 0/0."),
    "remake_shuffle_bean_souls": ("shuffle_beans", "Shuffle Bean Souls", None,
                                  "A magic bean soil (and its Gold Skulltula and leaf platform) only appears once you "
                                  "find its soul (Ship of Harkinian's Shuffle Bean Souls: 10 souls)."),
    # merchants (SoH: Shuffle Shops & Merchants)
    **_prices("merchant", "Merchants", "shuffle_expensive_merchants"),
    "remake_early_grannys_shop": ("shuffle_expensive_merchants", "Early Granny's Shop", None,
                                  "With expensive merchants shuffled and the adult trade not, Granny's item is in "
                                  "logic from the start (Ship of Harkinian)."),
    "remake_shuffle_beggar": ("shuffle_expensive_merchants", "Shuffle the Market Beggar", None,
                              "The beggar in the Market gives an item for a bottled item (Ship of Harkinian)."),
    "remake_shuffle_bowling_bombchus": ("shuffle_frog_song_rupees", "Shuffle Bombchu Bowling's Bombchus", None,
                                        "Bombchu Bowling's bombchu prize is shuffled too."),
    # fishing, after OoTR's loach prize (SoH: Shuffle Items' Fishsanity, Additional Items' Fishing Pole)
    "remake_fishsanity": ("shuffle_loach_reward", "Fishsanity",
                          {"off": "Off", "pond": "Fishing pond", "overworld": "Zora's Domain fish",
                           "both": "Pond and Zora's Domain"},
                          "Fish hold items: the fishing pond's fish (show one to the owner) and the fish in "
                          "Zora's Domain (net one with a bottle). Ship of Harkinian's Fishsanity."),
    "remake_fishsanity_pond_count": ("shuffle_loach_reward", "Pond Fish with Items", None,
                                     "How many of the pond's 17 fish hold items."),
    "remake_fishsanity_age_split": ("shuffle_loach_reward", "Child and Adult Pond Fish Apart", None,
                                    "The pond's fish are separate checks as a child and as an adult."),
    "remake_shuffle_fishing_pole": ("shuffle_loach_reward", "Shuffle the Fishing Pole", None,
                                    "The pond owner rents no rod until you find the Fishing Pole (Ship of Harkinian)."),
    "remake_shuffle_fishermans_hat": ("shuffle_loach_reward", "Shuffle the Fishing Pond Owner's Hat", None,
                                      "Giving the pond owner's hat back gives an item (Ship of Harkinian)."),
    # Main Rules > Shuffle Dungeon Items
    # (SoH: Shuffle Settings' Link's Pocket, Dungeon Items, Win Condition)
    "remake_links_pocket": ("shuffle_dungeon_rewards", "Link's Pocket",
                            {"ootr": "OoTR's rules", "reward": "A Spiritual Stone or Medallion",
                             "advancement": "An item you may need", "anything": "Anything", "nothing": "Junk"},
                            "What Rauru's reward in the Chamber of Sages is (with \"skip Rauru's reward\" free, you "
                            "start with it). Anything but OoTR's rules needs the rewards shuffled (Ship of "
                            "Harkinian / OoT3D Randomizer's Link's Pocket)."),
    "remake_links_pocket_reward": ("shuffle_dungeon_rewards", "Link's Pocket Reward",
                                   {"any": "Any reward", "stone": "A Spiritual Stone", "medallion": "A Medallion",
                                    "light_medallion": "The Light Medallion"},
                                   "Which reward Link's Pocket holds when it holds one (Ship of Harkinian)."),
    "remake_skeleton_key": ("keyring_give_bk", "Skeleton Key", None,
                            "One extra item that opens every small-key door in every dungeon and the Thieves' "
                            "Hideout (Ship of Harkinian's Skeleton Key)."),
    "remake_shuffle_boss_souls": ("shuffle_bosskeys", "Shuffle Boss Souls", None,
                                  "Each dungeon boss can only be fought once you find its soul (Ship of Harkinian's "
                                  "Shuffle Boss Souls). Without it, entering its arena sends you back to the "
                                  "dungeon's entrance."),
    "remake_shuffle_enemy_souls": ("shuffle_bosskeys", "Shuffle Enemy Souls",
                                   {"off": "Off", "all": "All enemies", "regional": "Regional"},
                                   "Enemies only appear once you find their soul (as the OotrR remake randomizer's "
                                   "enemy souls). All enemies: one soul for each kind of enemy, plus every boss's "
                                   "soul. Regional: one soul for each area, which also lets you fight its dungeon's "
                                   "boss. A room that shuts you in until its enemies are beaten stays open without "
                                   "their soul, and the logic asks for the souls a dungeon's puzzles and a guarded "
                                   "chest need. For boss souls only, use Shuffle Boss Souls."),
    "remake_ganons_soul": ("ganon_bosskey_hearts", "Ganon's Soul",
                           {"off": "Off", "stones": "Spiritual Stones", "medallions": "Medallions",
                            "dungeons": "Dungeon rewards", "tokens": "Gold Skulltula tokens", "hearts": "Hearts"},
                           "The door to Ganondorf opens only once you hold enough of these (Ship of Harkinian's "
                           "Ganon's Soul)."),
    "remake_ganons_soul_count": ("ganon_bosskey_hearts", "Ganon's Soul Count", None,
                                 "How many are needed: up to 3 Spiritual Stones, 6 Medallions, 9 dungeon rewards, "
                                 "100 tokens, or 4-20 hearts. 0: all of that kind."),
    "remake_shuffle_ganons_soul": ("ganon_bosskey_hearts", "Ganon's Soul as an Item", None,
                                   "The door to Ganondorf opens only once you find Ganon's Soul somewhere in the "
                                   "world (Ship of Harkinian's Ganon's Soul, Anywhere). Not with the count version."),
    "remake_silver_rupee_items": ("silver_rupee_pouches", "Silver Rupees Give an Item Too", None,
                                  "Every silver rupee still counts for its room, and taking it also gives a seed item "
                                  "(80 new checks)."),
    # Other > Timesavers (OoT3D Randomizer's too)
    "remake_skip_talon": ("no_epona_race", "Skip Waking Talon", None,
                          "Talon starts awake at Lon Lon Ranch (Ship of Harkinian). Malon's castle egg is skipped; "
                          "needs the Weird Egg and Chicken unshuffled."),
    "remake_skip_four_poes": ("useful_cutscenes", "Skip the Forest Temple's Four Poes Cutscene", None,
                              "The first time you enter the Forest Temple's main hall, the scene of the four Poes "
                              "taking the flames is skipped; what it changes in the temple still happens (OoT3D "
                              "Randomizer)."),
    "remake_skip_area_intros": ("useful_cutscenes", "Skip Area Intros", None,
                                "The short scene that shows off a place the first time you get there is skipped, "
                                "for 25 villages, fields and dungeon doorways. Anything a skipped arrival moves on "
                                "(a quest step, Navi's tip) still happens, and the place counts as visited on your "
                                "map. Intros that start a quest still play (OOTRR)."),
    "remake_skip_lake_owl": ("useful_cutscenes", "Skip the Lake Hylia Owl", None,
                             "Agreeing to fly with the owl at Lake Hylia skips the flight: you go straight to the "
                             "landing, or to the owl's shuffled destination (OoT3D Randomizer)."),
    "remake_skip_song_replays": ("fast_chests", "Skip Song Replays", None,
                                 "A played song takes effect right away; its tune still plays (OoT3D Randomizer)."),
    "remake_skip_pickup_text": ("fast_chests", "Skip Pickup Messages", None,
                                "No \"You got...\" box the first time you pick up a rupee, a heart, a magic jar, "
                                "arrows, seeds, nuts, sticks, bombs or bombchus (Ship of Harkinian, OOTRR). You "
                                "start with an empty nut bag and stick bag, since the first nut and stick were what "
                                "gave them."),
    "remake_faster_blocks": ("fast_chests", "Faster Block Push", None,
                             "Push blocks move twice as fast and still stop in the same spots (Ship of "
                             "Harkinian)."),
    "remake_skip_movies": ("fast_chests", "Skippable Opening and Credits", None,
                           "Lets you skip the opening movie and the credits movie, like every other cutscene "
                           "(OOTRR)."),
    "remake_king_zora_speed": ("fast_shadow_boat", "King Zora Moves", {"vanilla": "Slowly", "fast": "At once"},
                               "OoT3D Randomizer's King Zora speed."),
    # Other > Hints and Information
    # (SoH: Hints, Static Hints)
    "remake_hint_distribution": ("hint_dist", "Gossip Stone Hint Mix",
                                 {"off": "OoT Randomizer's (hint_dist)", "soh_useless": "Useless (Ship of Harkinian)",
                                  "soh_balanced": "Balanced (Ship of Harkinian)",
                                  "soh_strong": "Strong (Ship of Harkinian)",
                                  "soh_very_strong": "Very Strong (Ship of Harkinian)",
                                  "3ds_useless": "Useless (OoT3D Randomizer)",
                                  "3ds_balanced": "Balanced (OoT3D Randomizer)",
                                  "3ds_strong": "Strong (OoT3D Randomizer)",
                                  "3ds_very_strong": "Very Strong (OoT3D Randomizer)",
                                  "3ds_playthrough": "Playthrough (OoT3D Randomizer)"},
                                 "Use another randomizer's Gossip Stone hint mix instead of OoT Randomizer's."),
    "remake_hint_specificity": ("hint_dist", "Playthrough Hints Name", {"area": "The area", "exact": "The exact spot"},
                                "With the Playthrough mix: hints name an item's area or its exact spot (OoT3D "
                                "Randomizer)."),
    "remake_bonus_gossip_hints": ("hint_dist", "Bonus Song Hints", None,
                                  "With the Playthrough mix: the Sun's Song and warp songs get hints too (OoT3D "
                                  "Randomizer)."),
    "remake_extra_hints": ("misc_hints", "Extra Hints", None,
                           "Hints beyond OoTR's that this seed shows."),
    "remake_scrub_text_hint": ("misc_hints", "Scrubs Name Their Item", None,
                               "Every Business Scrub with a shuffled item says what it sells (Ship of Harkinian)."),
    "remake_loach_hint": ("misc_hints", "Pond Owner Names the Loach Prize", None,
                          "The fishing pond owner tells what keeping the Hyrule loach gives (Ship of Harkinian). "
                          "Needs the loach prize shuffled."),
    "remake_item_looks": ("potcrate_textures_specific", "Free-Standing Items Look Like",
                          {"item": "The real item", "heart": "A heart piece"},
                          "How heart pieces, heart containers and keys standing in the world show the item they "
                          "hold."),
    # Other > Gameplay Changes
    # (SoH: Logic's Blue Fire Arrows group; OoT3D Randomizer: Misc)
    "remake_damage_multiplier": ("damage_multiplier", "Damage x8 / x16",
                                 {"normal": "OoTR's damage multiplier", "x8": "x8", "x16": "x16"},
                                 "The two damage multipliers beyond OoTR's x4 (Ship of Harkinian / OoT3D "
                                 "Randomizer); logic treats both as one-hit KO."),
    "remake_slingshot_beehives": ("blue_fire_arrows", "Slingshot Breaks Beehives", None,
                                  "The Slingshot breaks beehives as the Bow already does (Ship of Harkinian)."),
    "remake_full_wallets": ("blue_fire_arrows", "Full Wallets", None,
                            "Every wallet comes full, and a new file starts with a full wallet (Ship of Harkinian)."),
    "remake_gk_durability": ("blue_fire_arrows", "Giant's Knife Durability", None,
                             "How many hits the Giant's Knife takes before it breaks (OoT3D Randomizer's GK "
                             "Durability; one number per seed)."),
    "remake_gk_durability_hits": ("blue_fire_arrows", "Giant's Knife Hits", None,
                                  "With \"A set number of hits\": how many, 1 to 999."),
    "remake_frog_song_timer": ("blue_fire_arrows", "Frog Song Time per Note", None,
                               "1 (vanilla) to 4 times the time per note in the frogs' final song (OoT3D "
                               "Randomizer)."),
    "remake_dpad_gear": ("blue_fire_arrows", "D-pad Gear Switching",
                         {"off": "Off", "hold": "Hold to switch", "wheel": "Wheel",
                          "wheel_tunics": "Wheel + tunics on D-pad left"},
                         "Hold D-pad up for your accessories (Lens of Truth, masks) and D-pad down for the Hover and "
                         "Iron Boots, without pausing. Hold to switch: keep holding and Link switches to the next one "
                         "every second (OOTRR), and a tap puts the gear on or takes it off. Wheel: the game's item "
                         "wheel opens on just that gear, letting go puts your pick on, and a tap toggles the gear "
                         "when you let go, so holding never does; it changes the game's code, so build the game again "
                         "in Longshot after installing. Wheel + tunics on D-pad left: the same, and holding D-pad left "
                         "opens a wheel of your tunics once you have the Goron or Zora Tunic; a tap on D-pad left "
                         "still plays the ocarina, when you let go."),
    "remake_navi_return": ("blue_fire_arrows", "Return with Navi",
                           {"off": "Off", "dungeons": "Dungeons", "everywhere": "Everywhere"},
                           "Press D-pad right and Navi offers a trip back, like the N64 game's save and quit (OOTRR). "
                           "Dungeons: inside a dungeon, back to its entrance. Everywhere: also home from the "
                           "overworld, Kokiri Forest as a child and the Temple of Time as an adult. Never in a boss or "
                           "miniboss fight or while a minigame timer runs. Navi's area tutorial hints are replaced by "
                           "it; her enemy hints stay."),
    # Other > Item Pool (OoT3D Randomizer's Item Pool,
    # SoH: Traps)
    "remake_avoid_vanilla_spots": ("item_pool_value", "No Item in Its Own Spot", None,
                                   "Off by default, as in OoT Randomizer, whose fill may put an item back in its own "
                                   "spot. Switch it on so that no check keeps its own vanilla item by chance."),
    "remake_vanilla_items": ("item_pool_value", "Items Stay in Their Vanilla Spots", None,
                             "Every item goes back to its own spot (OoT3D Randomizer's Vanilla logic). Needs vanilla "
                             "keys, maps and compasses, vanilla rewards and songs, and \"No item in its own spot\" off."),
    "remake_remove_double_defense": ("item_pool_value", "No Double Defense", None,
                                     "Double Defense becomes junk (OoT3D Randomizer)."),
    "remake_trap_weights": ("custom_ice_trap_count", "Trap Kinds", None,
                            "How often each trap kind replaces an ice trap, relative to the others (0: never)."),
    "remake_drop_ice_traps": ("ice_trap_appearance", "Ice Trap Appearance in Objects",
                              {"disguised": "Look like an item (recommended)", "classic": "A keese or a stand-in"},
                              "What an ice trap hidden in a pot, rock or grass looks like."),
    # Cosmetics > General Cosmetics, next to OoTR's controls
    # (D-pad display, first-person camera) and the parity/_show_models.py UI
    "remake_ocarina_controls": ("cosmetics_tab/generalcosmetics_section", "Ocarina Controls",
                                {"normal": "Normal (two-handed)", "classic": "Classic (one-handed)"},
                                "As in the game's Options. Ocarina note items show the button that plays their "
                                "note."),
    "remake_controller": ("cosmetics_tab/generalcosmetics_section", "Controller",
                          {"auto": "Auto (the controller Longshot is using)",
                           "nintendo": "Nintendo (A B X Y, L R)", "xbox": "Xbox (A B X Y, LB RB)",
                           "playstation": "PlayStation (cross circle square triangle, L1 R1)",
                           "steamdeck": "Steam Deck (A B X Y, L1 R1)"},
                          "The button labels Ocarina note items show."),
    # SFX > General (OoTR's randomize_all_sfx; OoT3D
    # Randomizer's Shuffle SFX)
    "remake_shuffle_all_sfx": ("randomize_all_sfx", "Shuffle Every Sound Effect", None,
                               "Every sound effect swaps with another of the same kind that the same actor already "
                               "has: a loop with a loop, a voice with a voice, a short sound with a short one (OoT3D "
                               "Randomizer's Shuffle SFX, categorical), footsteps and Link's voice included. The sound "
                               "settings below still choose their own sounds; music, fanfares and the ocarina keep "
                               "their settings."),
    # Remake only (see REMAKE_HOME)
    "remake_racing": (REMAKE_HOME, "Racing", None,
                      "Every racer's seed plays the same: options that change how long scenes take (fanfares, song "
                      "playbacks) are locked to the game's own."),
}

# Defaults for remake settings whose plugin has no REMAKE_DEFAULTS entry, meaning what the plugin reads when the
# setting isn't there. I checked shops.py, _dungeons_silver.py, no_vanilla.py, chests.py, hints.py and story.py. The
# app only writes a setting when it differs from its default. "No item in its own spot" is off by default (my call,
# for OoTR parity), and the three that used to follow it stay on by default by themselves.
DEFAULTS = {
    "remake_avoid_vanilla_spots": False,       # off, my call for OoTR parity
    "remake_shop_shields_tunics_after_found": False,
    "remake_shuffle_bowling_bombchus": True,   # on unless remake_avoid_vanilla_spots is set false explicitly
    "remake_split_potion_shops": True,         # on unless remake_avoid_vanilla_spots is set false explicitly
    "remake_silver_rupee_items": True,         # on unless remake_avoid_vanilla_spots is set false explicitly
    "remake_trap_weights": {"ice": 1},
    "remake_extra_hints": [],
    "remake_shuffle_master_sword": False,
    # the object shuffles, parity/drops.py _remake falls back to "off"
    **{f"remake_shuffle_{k}": "off" for k in ("grass", "rocks", "boulders", "trees", "icicles", "red_ice", "misc")},
}

# How the app shows remake settings whose plugin takes values that aren't a fixed list (REMAKE_SETTINGS None). Each
# entry is the schema type with its limits, like OoTR's sliders ("int" with min/max/step), or "choice"/"list" with
# [value, label] choices, where "enemies" means the enemizer's types. A "default" here is the app's, since the app
# only writes a setting when it differs.
TYPES = {}
for _kind in ("shop", "scrub", "merchant"):
    for _p in ("fixed", "range_1", "range_2"):
        TYPES[f"remake_{_kind}_price_{_p}"] = {"type": "int", "min": 0, "max": 500, "step": 5}
    for _w in ("none", "child", "adult", "giant"):
        TYPES[f"remake_{_kind}_price_weight_{_w}"] = {"type": "int", "min": 0, "max": 100}
TYPES["remake_gk_durability"] = {"type": "choice", "choices": [
    ["vanilla", "Vanilla (8 hits)"], ["random_risky", "Random, risky (1-128 hits, usually few)"],
    ["random_safe", "Random, safe (10-50 hits)"], ["fixed", "A set number of hits"]]}
TYPES["remake_gk_durability_hits"] = {"type": "int", "min": 1, "max": 999}
TYPES["remake_ganons_soul_count"] = {"type": "int", "min": 0, "max": 100, "default": 0}
TYPES["remake_enemizer_vanilla"] = {"type": "list", "choices": "enemies"}

# Rows the app greys out while another remake setting has a value, like OoTR's GUI does ("!v" means any value but v).
RULES = {"remake_gk_durability": [{"when": "!fixed", "settings": ["remake_gk_durability_hits"]}],
         "remake_ganons_soul": [{"when": "off", "settings": ["remake_ganons_soul_count"]}],
         "remake_enemizer": [{"when": "off", "settings": ["remake_enemizer_vanilla"]}],
         "remake_hint_distribution": [{"when": "!3ds_playthrough",
                                       "settings": ["remake_hint_specificity", "remake_bonus_gossip_hints"]}],
         "remake_links_pocket": [{"when": v, "settings": ["remake_links_pocket_reward"]}
                                 for v in ("advancement", "anything", "nothing")]}
for _kind in ("shop", "scrub", "merchant"):
    _k = f"remake_{_kind}_price"
    RULES[f"{_k}s"] = ([{"when": "!fixed", "settings": [f"{_k}_fixed"]},
                        {"when": "!range", "settings": [f"{_k}_range_1", f"{_k}_range_2"]},
                        {"when": "!wallet", "settings": [f"{_k}_weight_{w}" for w in ("none", "child", "adult",
                                                                                     "giant")]}]
                       + [{"when": v, "settings": [f"{_k}s_affordable"]} for v in ("ootr", "fixed", "affordable")])

# remake_trap_weights is the chests plugin's {kind: weight} table, and the app shows it as one number per trap kind.
# The app writes remake_trap_weight_<kind> and config/setting_aliases.json folds those back into the table. The whole
# table still works in a settings file.
# They sit under OoTR's "Ice Traps", so they're named as weights to keep the two from reading alike.
TRAP_KIND_LABELS = {"ice": "Ice Trap Weight", "shock": "Shock Trap Weight", "fire": "Fire Trap Weight",
                    "rupee": "Rupee Trap Weight"}
TRAP_KIND_TIPS = {k: f"How often a trap is {'an' if k == 'ice' else 'a'} {k} trap, against the other kinds' numbers "
                     f"(0: never)." for k in TRAP_KIND_LABELS}

