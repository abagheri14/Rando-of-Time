"""One seed played in a multiworld: the Archipelago connection, the checks read from the save and the running game,
and the received items handed to the game. The window (app.py) and the command line (__main__.py) both drive this.

Every ~2 s we read the newest save of this seed (any slot whose RandoAP_Seed_<seed_key> marker is true) and, when
the game runs, its live GameData. Done locations go to the server, and the goal too. The mailbox (delivery.py) runs
every 0.25 s while items wait, 1 s otherwise. A save or a running game of another seed is never read for checks and
never written to.
"""
import json
import os
import threading
import time
from collections import deque

from . import delivery as D
from . import live_memory
from .protocol import APClient, ClientError
from .savefile import SaveError, find_saves, load
from .seed import Seed, tracker_marks, tracker_settings_path

CHECK_SECONDS = 2.0
FAST_SECONDS, IDLE_SECONDS = 0.25, 1.0


def settings_dir():
    base = os.environ.get('APPDATA') or os.path.join(os.path.expanduser('~'), '.config')
    return os.path.join(base, 'RemakeRandoAP')  # the first name, kept like the app's (Randomizer.cs DataFolder)


def default_save_root():
    """The tracker's save folder (the player already chose it there), else Longshot's usual one if it exists."""
    try:
        with open(tracker_settings_path(), encoding='utf-8-sig') as stream:
            root = json.load(stream).get('SaveRoot')
        if root and os.path.isdir(root):
            return root
    except (OSError, ValueError, AttributeError):
        pass
    for root in (os.path.join(os.environ.get('LOCALAPPDATA', ''), 'LongshotLauncher', 'user', 'save'),):
        if root and os.path.isdir(root):
            return root
    return ''


def load_ids(folder=None):
    """{item id: name} of our game from data/archipelago/ids.json (before the server's DataPackage arrives)."""
    folder = folder or D.find_tables()
    try:
        with open(os.path.join(folder, 'ids.json'), encoding='utf-8') as stream:
            data = json.load(stream)
        return {int(i): str(n) for n, i in (data.get('items') or {}).items()}
    except (OSError, ValueError, TypeError, AttributeError):
        return {}


class SaveFinder:
    """The newest progress.sav under ``root`` that belongs to the seed (re-read only when a file changes)."""

    def __init__(self, seed, root='', path=''):
        self.seed, self.root, self.path = seed, root, path
        self.cache = {}            # path -> (stamp, SaveFile or None, owned)
        self.current, self.error = None, ''

    def poll(self):
        paths = [self.path] if self.path else find_saves(self.root)
        best = None
        for path in paths:
            try:
                stat = os.stat(path)
            except OSError:
                continue
            stamp = (stat.st_size, stat.st_mtime_ns)
            cached = self.cache.get(path)
            if cached is None or cached[0] != stamp:
                try:
                    save = load(path)
                except SaveError as error:
                    self.error = str(error)
                    if cached is None:
                        continue
                    save, owned = cached[1], cached[2]   # mid-write: keep the last good read
                else:
                    owned = self.seed.owns(save)
                    self.cache[path] = (stamp, save, owned)
            else:
                save, owned = cached[1], cached[2]
            if owned and save is not None and (best is None or save.written > best.written):
                best = save
        if best is None:
            self.error = ('no save of this seed yet' if paths else
                          f'no save found in {self.root}' if self.root else 'choose the save folder')
        else:
            self.error = ''
        self.current = best
        return best


class Session:
    def __init__(self, seed_folder, server, slot='', password='', save_root='', save_path='', live=True,
                 send_marks=True, cache_dir=None, game=None, connect=None, clock=time.monotonic, marks_path=None,
                 tables=None):
        self.seed = Seed(seed_folder)
        self.clock = clock
        self.send_marks, self.marks_path = send_marks, marks_path
        self.saves = SaveFinder(self.seed, save_root or default_save_root(), save_path)
        tables = tables or D.find_tables()
        self.ids = load_ids(tables)
        codes, version = D.load_codes(tables)
        self.codes, self.tables_version = codes, version
        self.client = APClient(self.seed.game, slot or self.seed.slot_name, server, password,
                               items_handling=self.seed.items_handling, seed=self.seed.seed,
                               mailbox_version=self.seed.mailbox_version,
                               locations=self.seed.location_ids.values(), location_names=self.seed.location_names,
                               cache_dir=cache_dir if cache_dir is not None else os.path.join(settings_dir(),
                                                                                              'datapackage'),
                               connect=connect)
        # the running game: given (tests), else live memory where this system has it
        if game is None and live and live_memory.supported():
            game = live_memory.LiveGameData(writable=D.WRITABLE)
        self.live = game
        self.mailbox = D.Delivery(D.GameMailbox(game) if isinstance(game, live_memory.LiveGameData) else game,
                                  self.seed.seed_key, codes, clock=clock) if game is not None else None
        self._events = deque(maxlen=2000)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self.done = set()              # Keep checks reported earlier in this session.
        self.goal = False
        self.game_status, self.save_status = 'not looked yet', ''
        self.live_owned = False
        self._next_check = 0.0
        if self.mailbox is not None and not codes:
            self._event('error', 'data/archipelago/mailbox.json is missing: received items cannot be handed over.')
        if self.seed.marker is None:
            self._event('error', 'This seed has no seed_key in ap.json: its saves cannot be told from other seeds\', '
                                 'so the running game is not read and received items are not handed over.')

    # Public
    def start(self):
        self.client.start()
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name='archipelago-game', daemon=True)
            self._thread.start()

    def stop(self):
        self._stop.set()
        self.client.stop()
        if self._thread is not None:
            self._thread.join(timeout=3)

    def say(self, text):
        self.client.say(text)

    def events(self):
        with self._lock:
            mine = list(self._events)
            self._events.clear()
        return sorted(mine + self.client.events(), key=lambda e: e.get('time', 0))

    def summary(self):
        s = self.client.summary()
        mailbox = self.mailbox
        s.update(game=self.game_status, save=self.save_status, goal=self.seed.goal.text, goal_reached=self.goal,
                 delivery=mailbox.status if mailbox else 'items are not handed over on this system',
                 in_game=mailbox.count if mailbox else None,
                 to_hand_over=(mailbox.waiting if mailbox and mailbox.count is not None else None),
                 checks_done=len(self.done), seed_name=self.seed.seed_name or s.get('seed_name'))
        return s

    # The game side
    def _event(self, kind, text, **extra):
        with self._lock:
            self._events.append(dict(extra, kind=kind, text=text, time=time.time()))

    def item_name(self, item_id):
        names = ((self.client.names.get(self.seed.game) or {}).get('item') or {})
        return names.get(item_id) or self.ids.get(item_id)

    def received_names(self):
        return [self.item_name(entry.get('item')) for entry in self.client.received_items()]

    def _run(self):
        while not self._stop.is_set():
            now = self.clock()
            if now >= self._next_check:
                self._next_check = now + CHECK_SECONDS
                try:
                    self.check_once()
                except Exception as error:  # noqa: BLE001 - never stop for one bad read
                    self._event('error', f'Reading the game failed: {error}')
            busy = False
            try:
                busy = self.deliver_once()
            except Exception as error:  # noqa: BLE001
                self._event('error', f'Item hand-over failed: {error}')
            self._stop.wait(FAST_SECONDS if busy else IDLE_SECONDS)

    def check_once(self):
        """Reads the save and the running game; tells the client what is done and whether the goal is reached."""
        save = self.saves.poll()
        if save is not None:
            slot = os.path.basename(os.path.dirname(save.path)) or save.path
            self.save_status = f"{slot} · saved {time.strftime('%H:%M', time.localtime(save.written))}"
        else:
            self.save_status = self.saves.error
        snap = None
        if self.live is not None and self.seed.marker is not None and hasattr(self.live, 'snapshot'):
            try:
                snap = self.live.snapshot()
                self.live_owned = self.seed.owns(snap)
                name = self.live.describe() if hasattr(self.live, 'describe') else 'game'
                self.game_status = f'{name}: ' + ('a save of this seed is loaded' if self.live_owned else
                                                  'no save of this seed loaded')
                if not self.live_owned:
                    snap = None
            except live_memory.LiveUnavailable as error:
                self.game_status, self.live_owned = f'game: {error}', False
        elif self.live is None:
            self.game_status = 'the running game is not read on this system: checks come from the save'
        elif self.seed.marker is None:
            self.game_status = 'not read: this seed has no seed_key, so its saves cannot be told apart'
        marks = tracker_marks(self.seed.tracker_seed, self.marks_path) if self.send_marks else []
        done = self.seed.done_locations(save, snap, marks)
        new = done - self.done
        if new:
            self.done |= new
        if not self.goal and self.seed.goal_reached(save, snap):
            self.goal = True
            self._event('goal', f'Goal reached ({self.seed.goal.text}).')
        self.client.update(self.done, self.goal)
        return new

    def deliver_once(self):
        """One mailbox turn; True while items wait (poll fast)."""
        mailbox = self.mailbox
        if mailbox is None:
            return False
        if self.seed.marker is None:
            mailbox.status = 'not handed over: this seed has no seed_key in ap.json'
            return False
        names = self.received_names()
        if not names:
            mailbox.status = 'nothing received yet' if self.client.connected else 'not connected'
            return False
        try:
            index = mailbox.step(names)
        except live_memory.LiveUnavailable as error:
            mailbox.status = f'game not reachable ({error}): {len(names)} received item(s) wait'
            return False
        except PermissionError as error:   # a non-mailbox key: a bug, never written
            mailbox.status = str(error)
            self._event('error', str(error))
            return False
        received = self.client.received_items()
        for kind, i in mailbox.mailbox.take_notes():
            entry = received[i] if i < len(received) else {}
            item, sender, _ = self.client.describe_received(entry) if entry else (f'item {i + 1}', '?', '')
            if kind == 'delivered':
                self._event('delivered', f'In game: {item} (from {sender})', index=i)
            elif kind == 'aside':
                self._event('error', f'{item} (from {sender}) was not taken by the game after {D.MAX_SIGNALS} '
                                     'tries: tried again in a minute. A menu, a cutscene or a loading zone may be '
                                     'in the way.', index=i)
            elif kind == 'no_code':
                self._event('error', f'{item} (from {sender}) is unknown to this patch: the game counts it and '
                                     'gives nothing. Update the randomizer.', index=i)
            elif kind == 'retry':
                self._event('log', f'Handing over {item} again (the game did not count it).', index=i)
        if index is not None and mailbox.mailbox.signals == 1:
            entry = received[index] if index < len(received) else {}
            item, sender, _ = self.client.describe_received(entry) if entry else ('?', '?', '')
            self._event('log', f'Handing over {item} (from {sender})...', index=index)
        return bool(mailbox.waiting)


__all__ = ['Session', 'ClientError', 'settings_dir', 'default_save_root']
