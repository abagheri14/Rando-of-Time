"""One Archipelago seed on this machine: its ``ap.json`` (slot info and location ids, written by build_patch.py; see
data/archipelago/CONTRACT.md) and its ``tracker.json`` (every check with the save flags that say it is done).

A check is done when any of its flags is set, as in the tracker (tracker/app/MainForm.cs FlagSet):
  b64   {"t": "b64", "h": "<u64>"}            a placement hash in the save's Bool64bitKey list
  bit   {"t": "bit", "a": "<array>", "i": N}  element N of a saved bool array (RandoChecked)
  bool  {"t": "bool", "n": "<name>"}          a named saved Bool
Checks without a flag (NPC gifts, songs, shops, scrubs in older seeds) can only be sent when the player marks them
in the tracker (its marks are read from the tracker's settings, see ``tracker_marks``).
"""
import json
import os

from .goal import seed_goal
from .savefile import murmur3

AP_FILE = 'ap.json'
TRACKER_FILE = 'tracker.json'
DEFAULT_GAME = 'Rando of Time'
MARKER_PREFIX = 'RandoAP_Seed_'
FOUND_PREFIX = 'RandoAP_Found_'


class SeedError(Exception):
    """The folder is not an Archipelago seed of ours (or its files are broken)."""


class Flag:
    __slots__ = ('kind', 'hash', 'name', 'key', 'index')

    def __init__(self, raw):
        self.kind = str(raw.get('t') or '')
        self.hash = int(raw['h']) if raw.get('h') not in (None, '') else None
        self.name = raw.get('n') or raw.get('a')
        self.key = murmur3(self.name) if self.name else None
        self.index = int(raw['i']) if raw.get('i') not in (None, '') else None

    def in_save(self, save):
        if save is None:
            return False
        if self.kind == 'b64':
            return self.hash is not None and save.has64(self.hash)
        if self.kind == 'bit':
            return self.name is not None and self.index is not None and save.bit(self.key, self.index) is True
        if self.kind == 'bool':
            return self.key is not None and save.bool(self.key) is True
        return False

    def in_live(self, live):
        """Whether a live memory snapshot shows the flag (None: the snapshot can't tell; bool arrays aren't read)."""
        if not live:
            return None
        if self.kind == 'bool' and self.key is not None:
            value = (live.get('bool') or {}).get(self.key)
            return None if value is None else bool(value)
        if self.kind == 'b64' and self.hash is not None and live.get('bool64_complete'):
            return self.hash in (live.get('bool64') or {})
        return None


class Check:
    __slots__ = ('name', 'kind', 'flags', 'location_id')

    def __init__(self, raw, location_id):
        self.name = raw['name']
        self.kind = raw.get('kind') or 'check'
        self.flags = [Flag(f) for f in raw.get('flags') or () if isinstance(f, dict)]
        self.location_id = location_id

    def done(self, save, live=None):
        return any(f.in_save(save) or f.in_live(live) is True for f in self.flags)


def _first(data, *names, default=None):
    for name in names:
        if data.get(name) not in (None, ''):
            return data[name]
    return default


class Seed:
    """``folder``: the seed's output folder (OUT), holding ap.json and tracker.json."""

    def __init__(self, folder):
        self.folder = os.path.abspath(folder)
        path = os.path.join(self.folder, AP_FILE)
        if not os.path.isfile(path):
            raise SeedError(f'no {AP_FILE} in {self.folder}: this seed was not built from an Archipelago patch')
        try:
            with open(path, encoding='utf-8') as stream:
                self.ap = json.load(stream)
        except (OSError, ValueError) as error:
            raise SeedError(f'{path}: {error}') from None
        if not isinstance(self.ap, dict):
            raise SeedError(f'{path}: not an object')
        ap = self.ap
        self.game = str(_first(ap, 'game', default=DEFAULT_GAME))
        self.slot_name = str(_first(ap, 'slot_name', 'player_name', 'name', default=''))
        self.seed_name = str(_first(ap, 'seed_name', default=''))
        # our generator's seed. Connected.slot_data["seed"] has to match, or this patch is another slot's
        self.seed = _first(ap, 'seed')
        self.seed = None if self.seed is None else str(self.seed)
        # MAILBOX.md: the save marker RandoAP_Seed_<seed_key>, true only in saves of this seed
        self.seed_key = _first(ap, 'seed_key')
        self.seed_key = None if self.seed_key is None else str(self.seed_key)
        self.marker = murmur3(f'{MARKER_PREFIX}{self.seed_key}') if self.seed_key else None
        self.slot = _first(ap, 'slot')
        self.mailbox_version = _first(ap, 'mailbox_version')
        self.version = _first(ap, 'client_version', 'ap_version')
        self.foreign = _first(ap, 'foreign', default={}) or {}
        self.start_inventory = _first(ap, 'start_inventory', default={}) or {}
        locations = _first(ap, 'locations', 'location_ids', 'location_name_to_id', default={})
        if not isinstance(locations, dict) or not locations:
            raise SeedError(f'{path}: no location ids')
        self.location_ids = {str(name): int(ident) for name, ident in locations.items()}
        self.location_names = {ident: name for name, ident in self.location_ids.items()}
        items = _first(ap, 'items', 'item_ids', 'item_name_to_id', default={})
        self.item_ids = {str(n): int(i) for n, i in items.items()} if isinstance(items, dict) else {}
        # CONTRACT.md: own items at own locations are already in the seed, and the server only sends other worlds'
        # items and the starting inventory
        self.items_handling = int(_first(ap, 'items_handling', default=0b101))
        tracker = os.path.join(self.folder, str(_first(ap, 'tracker', default=TRACKER_FILE)))
        self.checks, self.tracker_seed = self._load_checks(tracker)
        self.by_name = {c.name: c for c in self.checks}
        # locations of the AP table that tracker.json doesn't list (no spot, no flag of their own)
        for name, ident in self.location_ids.items():
            if name not in self.by_name:
                check = Check({'name': name}, ident)
                self.checks.append(check)
                self.by_name[name] = check
        # MAILBOX.md: a location holding another player's item also sets the saved Bool RandoAP_Found_<location id>.
        # We read it for every AP location, since a patch may set it at flagless own-item spots too, and a Bool the
        # patch doesn't have is just absent (never "done").
        for check in self.checks:
            if check.location_id is not None:
                check.flags.append(Flag({'t': 'bool', 'n': f'{FOUND_PREFIX}{check.location_id}'}))
        self.goal = seed_goal(self.folder, _first(ap, 'goal'))

    def owns(self, data):
        """Whether a save (SaveFile) or a live snapshot belongs to this seed, meaning its marker is true. Without a
        seed_key (older patches) there's no way to tell, so every save counts."""
        if self.marker is None:
            return True
        if data is None:
            return False
        if isinstance(data, dict):
            return (data.get('bool') or {}).get(self.marker) is True
        return data.bool(self.marker) is True

    def _load_checks(self, path):
        if not os.path.isfile(path):
            raise SeedError(f'no {os.path.basename(path)} in {self.folder} (build_data.py seed makes it)')
        try:
            with open(path, encoding='utf-8') as stream:
                data = json.load(stream)
        except (OSError, ValueError) as error:
            raise SeedError(f'{path}: {error}') from None
        checks = [Check(c, self.location_ids.get(c.get('name'))) for c in data.get('checks') or ()
                  if isinstance(c, dict) and c.get('name')]
        return checks, str(data.get('seed') or '')

    # Evaluation
    def tracked(self):
        """Checks that have a location id and a save flag."""
        return [c for c in self.checks if c.location_id is not None and c.flags]

    def done_locations(self, save, live=None, marked=()):
        """Location ids of the checks the save (or the running game) shows done, plus the ``marked`` check names."""
        done = {c.location_id for c in self.checks if c.location_id is not None and c.done(save, live)}
        for name in marked:
            check = self.by_name.get(name)
            if check is not None and check.location_id is not None:
                done.add(check.location_id)
        return done

    def goal_reached(self, save, live=None):
        return self.goal.reached(save, live)


def tracker_settings_path():
    """The tracker's settings file (tracker/app/MainForm.cs AppSettings: %APPDATA%/RemakeRandoTracker/settings.json)."""
    base = os.environ.get('APPDATA') or os.path.join(os.path.expanduser('~'), '.config')
    return os.path.join(base, 'RemakeRandoTracker', 'settings.json')


def tracker_marks(seed_id, path=None):
    """Check names the player marked by hand in the tracker for this seed (its tracker.json "seed")."""
    path = path or tracker_settings_path()
    try:
        with open(path, encoding='utf-8-sig') as stream:
            settings = json.load(stream)
    except (OSError, ValueError):
        return []
    marks = (settings.get('Manual') or {}).get(seed_id) if isinstance(settings, dict) else None
    return [str(m) for m in marks] if isinstance(marks, list) else []
