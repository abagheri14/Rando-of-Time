"""Rando of Time: the Ocarina of Time remake (Longshot, Rekarina, Switch, emulators) in Archipelago.

Built with tools/archipelago/build_apworld.py into rando_of_time.apworld (Archipelago's custom_worlds).

How it works:
- Our generator (tools/rando/generate.py, which is OoT Randomizer with the remake's logic and plugins) builds each
  player's world, in the randomizer folder set in host.yaml (rando_of_time_options). It runs in its own Python
  process, one per player (tools/archipelago/worker.py). OoTR's modules share names with Archipelago's, our
  generator needs PYTHONHASHSEED=0 to rebuild a world exactly, and its plugins need the randomizer's packages.
  Pointing at the installed randomizer also means there's only one copy of our logic, so an apworld never runs
  older rules than the randomizer that builds the seed.
- The world stops where OoTR's fill would start its main fill. Whatever our rules place before that (shop items,
  songs on song spots, dungeon-bound items) becomes locked items, and the main fill's pool is this world's item
  pool.
- One region holds every location, like OotrR's apworld does. A location's access rule is "reachable with this
  player's collected items". Our logic engine answers it (OoTR's own Search, same as the tracker's logic server)
  and it's cached by item counts. Item rules are our generator's item rules.
- Output: one .aprr per player (data/archipelago/CONTRACT.md). `python tools/archipelago/build_patch.py FILE OUT`
  turns it into a normal seed folder.

Structure ported from OotrR's apworld (github.com/Mozencaz/OotrR, src/oot_rando/archipelago/ap_world.py.in;
MIT License, Copyright (c) 2026 Mozencaz; see LICENSE-OotrR.txt).
"""
import collections
import json
import os
import pkgutil
import string
import typing

import settings
from BaseClasses import Item, ItemClassification, Location, LocationProgressType, Region
from Options import OptionError
from worlds.AutoWorld import WebWorld, World

from .options import RandoOfTimeOptions, our_settings
from .worker_client import PlayerLogic, Worker, WorkerError, check_slot

GAME = "Rando of Time"
FORMAT, VERSION = "rando-of-time-ap", 1
WORLD_VERSION = "0.9.0"
IDS = json.loads(pkgutil.get_data(__name__, "ids.json").decode("utf-8"))
CLASSIFICATION = {"progression": ItemClassification.progression, "useful": ItemClassification.useful,
                  "filler": ItemClassification.filler, "trap": ItemClassification.trap}


class RandoOfTimeSettings(settings.Group):
    class RandomizerFolder(settings.UserFolderPath):
        """Rando of Time's folder (it holds tools/rando/generate.py). Archipelago runs our generator from
        there to build each player's world."""
        description = "Rando of Time folder"

    class PythonPath(str):
        """The Python that runs the randomizer. Leave it empty for the randomizer's own python\\python.exe, or else the
        Python launcher (py -3) or python on PATH."""

    randomizer_folder: RandomizerFolder = RandomizerFolder("Rando-of-Time")
    python: PythonPath = PythonPath("")


class RandoOfTimeWeb(WebWorld):
    theme = "grass"


class RandoOfTimeItem(Item):
    game = GAME


class RandoOfTimeLocation(Location):
    game = GAME


def classification_name(flags):
    flags = int(flags)
    if flags & int(ItemClassification.progression):
        return "progression"
    if flags & int(ItemClassification.trap):
        return "trap"
    if flags & int(ItemClassification.useful):
        return "useful"
    return "filler"


class RandoOfTimeWorld(World):
    """The Ocarina of Time remake, randomized by Rando of Time: OoT Randomizer's own logic with the
    remake's rules and features."""

    game = GAME
    web = RandoOfTimeWeb()
    options_dataclass = RandoOfTimeOptions
    options: RandoOfTimeOptions
    settings: typing.ClassVar[RandoOfTimeSettings]
    settings_key = "rando_of_time_options"
    topology_present = False
    item_name_to_id = IDS["items"]
    location_name_to_id = IDS["locations"]

    # The randomizer
    @classmethod
    def host(cls):
        """(randomizer folder, python). The RANDO_OF_TIME / RANDO_OF_TIME_PYTHON environment variables come first (for
        tests or several installs), otherwise host.yaml."""
        folder = os.environ.get("RANDO_OF_TIME")
        python = os.environ.get("RANDO_OF_TIME_PYTHON", "")
        if not folder:
            folder = str(cls.settings.randomizer_folder)
            python = python or str(cls.settings.python or "")
        return folder, python

    def generate_early(self):
        self.seed_text = str(self.random.getrandbits(32))
        # this seed's identity in saves, the mailbox's RandoAP_Seed_<seed_key> (data/archipelago/MAILBOX.md)
        self.seed_key = "".join(self.random.choice(string.ascii_letters + string.digits) for _ in range(12))
        self.our_options = our_settings(self.options)
        folder, python = self.host()
        try:
            self.worker = Worker(folder, python)
        except (OSError, WorkerError) as e:
            raise OptionError(f"{GAME} ({self.player_name}): {e}") from e
        # Start each player in its own process. create_regions collects the results.
        self.worker.start({"cmd": "build", "seed": self.seed_text, "options": self.our_options,
                           "seed_key": self.seed_key})
        self._world = None

    @property
    def desc(self):
        if self._world is None:
            try:
                self._world = self.worker.finish()["world"]
            except WorkerError as e:
                raise OptionError(f"{GAME} ({self.player_name}): {e}") from e
            missing_l = [n for n in self._world["locations"] if n not in self.location_name_to_id]
            missing_i = [n for n in self._world["items"] if n not in self.item_name_to_id]
            if missing_l or missing_i:
                raise OptionError(f"{GAME}: this apworld is older than the randomizer ({len(missing_l)} locations, "
                                  f"{len(missing_i)} items without an id, e.g. {(missing_l + missing_i)[:3]}): build "
                                  "it again with tools/archipelago/build_apworld.py")
            self.logic = PlayerLogic(self.worker, self._world)
        return self._world

    # World
    def create_regions(self):
        world, player = self.desc, self.player
        logic = self.logic
        menu = Region("Menu", self.player, self.multiworld)
        rules = logic.item_rules()
        excluded = set(world["excluded"])
        self.ap_locations = []
        for i, name in enumerate(world["locations"]):
            loc = RandoOfTimeLocation(player, name, self.location_name_to_id[name], menu)
            loc.access_rule = (lambda state, i=i: logic.reachable(i, state.prog_items[player]))
            own, foreign = rules[i]
            loc.item_rule = (lambda item, own=own, foreign=foreign:
                             item.name in own if item.player == player and item.game == GAME else foreign)
            if i in excluded:
                loc.progress_type = LocationProgressType.EXCLUDED
            menu.locations.append(loc)
            self.ap_locations.append(loc)
        self.multiworld.regions.append(menu)
        for i, item in world["locked"].items():
            self.ap_locations[int(i)].place_locked_item(self.create_item(item))
        # items our rules keep to this world's regions (dungeon items "in their dungeon", "overworld"...)
        self.options.local_items.value |= {n for n, c in world["items"].items() if c["local"]}

    def create_item(self, name):
        world = self.desc
        kind = world["items"].get(name, {}).get("class") or ("progression" if name in self.logic.progression
                                                              else "filler")
        return RandoOfTimeItem(name, CLASSIFICATION[kind], self.item_name_to_id[name], self.player)

    def create_items(self):
        for name in self.desc["pool"]:
            self.multiworld.itempool.append(self.create_item(name))

    def get_filler_item_name(self):
        return self.desc["filler"]

    def set_rules(self):
        logic, player = self.logic, self.player
        self.multiworld.completion_condition[player] = lambda state: logic.reach(state.prog_items[player])[1]

    # Output
    def fill_slot_data(self):
        return {"world_version": WORLD_VERSION, "seed": self.desc["seed"], "seed_key": self.seed_key,
                "mailbox_version": self.desc["mailbox_version"], "death_link": False}

    def aprr(self):
        """This player's .aprr (data/archipelago/CONTRACT.md)."""
        mw, player, world = self.multiworld, self.player, self.desc
        locked = set(world["locked"])
        placements = {}
        for i, loc in enumerate(self.ap_locations):
            item = loc.item
            own = item.player == player and item.game == GAME
            placements[loc.name] = {"item": item.name, "item_id": item.code, "player": item.player,
                                    "player_name": mw.get_player_name(item.player), "game": item.game, "own": own,
                                    "classification": classification_name(item.classification),
                                    "flags": int(item.classification), "location_id": loc.address,
                                    "locked": str(i) in locked}
        remote = [{"item": loc.item.name, "location": loc.name, "location_id": loc.address, "player": loc.player,
                   "player_name": mw.get_player_name(loc.player)}
                  for loc in mw.get_locations()
                  if loc.item is not None and loc.address is not None and loc.item.player == player
                  and loc.player != player]
        start = collections.Counter(item.name for item in mw.precollected_items[player])
        players = {str(p): {"name": mw.get_player_name(p), "game": mw.worlds[p].game} for p in mw.player_ids}
        return {"format": FORMAT, "version": VERSION, "game": GAME, "world_version": WORLD_VERSION,
                "seed_name": mw.seed_name, "seed": world["seed"], "settings": world["settings"],
                "plugins": world["plugins"], "slot": player, "slot_name": mw.get_player_name(player), "team": 0,
                "players": players, "placements": placements, "fixed": world.get("fixed") or {}, "remote": remote,
                "start_inventory": dict(start),
                "world_check": {"world": world["world_check"], "attempt": world["attempt"],
                                "locations": sorted(world["locations"])},
                "mailbox_version": world["mailbox_version"]}

    def generate_output(self, output_directory):
        path = os.path.join(output_directory, self.multiworld.get_out_file_name_base(self.player) + ".aprr")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.aprr(), f, ensure_ascii=False, indent=1)
        # Run the post-fill checks now so a broken slot fails during generation.
        # RANDO_OF_TIME_NO_CHECK=1 skips this build check.
        if os.environ.get("RANDO_OF_TIME_NO_CHECK") != "1":
            folder, python = self.host()
            ok, message = check_slot(folder, python, path)
            if not ok:
                raise Exception(f"{GAME} ({self.player_name}): our generator can't build this slot's seed "
                                f"(generate again with another seed):" + chr(10) + message)
