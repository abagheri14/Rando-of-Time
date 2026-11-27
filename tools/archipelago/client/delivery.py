# The retry and set-aside timing is ported from OotrR (github.com/Mozencaz/OotrR, src/oot_rando/archipelago/receive.py).
# Copyright (c) 2026 Mozencaz. MIT License: see LICENSE-OotrR.txt in this folder.
"""Handing received items to the running game, through the mailbox of data/archipelago/MAILBOX.md (version 1).

GameData Bools (all saved with the file):
  RandoAP_Seed_<seed_key>      game   this save is this seed's: nothing is written unless it is true
  RandoAP_Count0..15           game   how many received items the game has taken (binary, bit 0 = 1): the receipt
  RandoAP_Code0..9             client the item code (mailbox.json "codes"), binary
  RandoAP_Idx0..3              client low 4 bits of the received-item index being delivered
  RandoAP_Signal               client sets it, the game clears it when it starts the item's event

One item at a time, in server order, and item ``Count`` is the next one. Idx is first written to (n+1)&15, which
invalidates the old code while it changes, then Code, then Idx = n&15, then Signal last. The event only gives the
item when Idx matches Count's low bits, so a repeated signal is harmless.

Retries work like OotrR's receive.py. An item whose Count hasn't moved RETRY_SECONDS after the game took the Signal
gets signalled again. After MAX_SIGNALS signals it's reported and waits ASIDE_SECONDS before the next tries. It can't
go behind the others like in OotrR, because the game counts items in order, but that pause keeps a dropped event from
flooding the game. A Signal that's still true means the game hasn't looked yet (pause menu, cutscene, loading), so no
retry is counted while it waits.

The game's Count is the only record of what was delivered, so a reconnect, a restart of this client or a reload of
an older save never gives an item twice and never loses one.
"""
import json
import os
import time

from .savefile import murmur3

RETRY_SECONDS = 8.0
MAX_SIGNALS = 5
ASIDE_SECONDS = 60.0
COUNT_BITS, CODE_BITS, IDX_BITS = 16, 10, 4
SUPPORTED_VERSIONS = (1,)

COUNT = [f'RandoAP_Count{i}' for i in range(COUNT_BITS)]
CODE = [f'RandoAP_Code{i}' for i in range(CODE_BITS)]
IDX = [f'RandoAP_Idx{i}' for i in range(IDX_BITS)]
SIGNAL = 'RandoAP_Signal'
WRITTEN = CODE + IDX + [SIGNAL]
WRITABLE = frozenset(murmur3(name) for name in WRITTEN)   # the only keys this client may ever write


def bits(value, names):
    """[(name, bool)] of ``value`` in binary over ``names`` (bit 0 first)."""
    return [(name, bool((value >> i) & 1)) for i, name in enumerate(names)]


def number(values, names):
    """The number the Bools ``names`` hold (``values``: {name: bool or None}); None when one is unknown."""
    total = 0
    for i, name in enumerate(names):
        value = values.get(name)
        if value is None:
            return None
        total |= int(bool(value)) << i
    return total


def signal_writes(index, code):
    """The writes that hand item ``index`` (its ``code``) to the game, in MAILBOX.md's order."""
    if not 0 <= code < 1 << CODE_BITS:
        raise ValueError(f'item code {code} out of range')
    return bits((index + 1) & 15, IDX) + bits(code, CODE) + bits(index & 15, IDX) + [(SIGNAL, True)]


def find_tables(start=None):
    """data/archipelago of this randomizer (beside tools/): ids.json and mailbox.json."""
    here = os.path.abspath(start or os.path.dirname(__file__))
    for _ in range(6):
        candidate = os.path.join(here, 'data', 'archipelago')
        if os.path.isdir(candidate):
            return candidate
        here = os.path.dirname(here)
    return None


def load_codes(folder=None):
    """({OoTR item name: code}, mailbox_version) from mailbox.json; ({}, None) when it isn't there."""
    folder = folder or find_tables()
    path = os.path.join(folder, 'mailbox.json') if folder else None
    try:
        with open(path, encoding='utf-8') as stream:
            data = json.load(stream)
    except (OSError, ValueError, TypeError):
        return {}, None
    codes = data.get('codes') if isinstance(data, dict) else None
    if not isinstance(codes, dict):
        return {}, data.get('mailbox_version') if isinstance(data, dict) else None
    return {str(k): int(v) for k, v in codes.items()}, data.get('mailbox_version')


class Mailbox:
    """What to write now (pure: no game access, no clock of its own). ``codes``: {item name: code}."""

    def __init__(self, codes):
        self.codes = dict(codes)
        self.index = None          # the item being handed over
        self.signals = 0           # signals sent for it
        self.signal_up = False     # True while the game still needs to clear Signal.
        self.taken_at = None       # When the client saw Signal return to false.
        self.sent_at = None
        self.aside_until = 0.0
        self.notes = []            # things to tell the player, drained by take_notes()
        self._no_code = set()
        self.last_count = None

    def take_notes(self):
        notes, self.notes = self.notes, []
        return notes

    def _new_item(self, index):
        self.index, self.signals, self.signal_up, self.taken_at, self.sent_at = index, 0, False, None, None
        self.aside_until = 0.0

    def step(self, names, state, now):
        """[(name, bool)] to write now, or None. ``names`` is the received item names in server order (None when not
        known yet), and ``state`` is {'marker': bool, 'count': int or None, 'signal': bool or None} read from the
        game."""
        if not state.get('marker'):
            return None
        count, signal = state.get('count'), state.get('signal')
        if count is None or signal is None:
            return None
        if self.last_count is not None and count > self.last_count:
            for i in range(self.last_count, min(count, len(names))):
                self.notes.append(('delivered', i))
        self.last_count = count
        if count >= len(names):
            self._new_item(None)
            return None
        if self.index != count:
            self._new_item(count)
        if signal:
            # Either ours and not taken yet (menu, cutscene, loading), or a Signal some other client set. Wait for the
            # game.
            return None
        if self.signal_up:
            self.signal_up, self.taken_at = False, now
        if self.taken_at is not None and now - self.taken_at < RETRY_SECONDS:
            return None
        if self.sent_at is not None and self.taken_at is None and now - self.sent_at < RETRY_SECONDS:
            return None
        if now < self.aside_until:
            return None
        if self.signals >= MAX_SIGNALS:
            self.signals = 0
            self.aside_until = now + ASIDE_SECONDS
            self.taken_at = None
            self.notes.append(('aside', count))
            return None
        name = names[count]
        if name is None:
            return None            # the item's name isn't known yet (DataPackage): never guess a code
        code = self.codes.get(name)
        if code is None:
            code = 0
            if count not in self._no_code:
                self._no_code.add(count)
                self.notes.append(('no_code', count))
        self.signals += 1
        self.signal_up, self.taken_at, self.sent_at = True, None, now
        if self.signals > 1:
            self.notes.append(('retry', count))
        return signal_writes(count, code)


class Delivery:
    """The mailbox bound to a game: ``game`` has ``read_bools(names) -> {name: bool or None}`` and
    ``write_bools([(name, bool)])`` (live_memory.LiveMailbox, or the tests' fake game)."""

    def __init__(self, game, seed_key, codes, clock=time.monotonic):
        self.game = game
        self.marker = f'RandoAP_Seed_{seed_key}' if seed_key else None
        self.mailbox = Mailbox(codes)
        self.clock = clock
        self.status = 'waiting for the game'
        self.count = None          # the game's Count at the last read
        self.waiting = 0

    def read_state(self):
        names = COUNT + [SIGNAL] + ([self.marker] if self.marker else [])
        values = self.game.read_bools(names)
        return {'marker': bool(values.get(self.marker)) if self.marker else True,
                'known': values.get(SIGNAL) is not None,
                'count': number(values, COUNT), 'signal': values.get(SIGNAL)}

    def step(self, names):
        """One turn. ``names``: received item names in server order. Returns the index signalled, or None.
        Raises live_memory.LiveUnavailable while the game can't be read."""
        if not self.marker:
            self.status = 'this seed has no seed_key in ap.json: items are not handed over'
            return None
        state = self.read_state()
        if not state['known'] or state['count'] is None:
            self.status = 'the running game has no mailbox (a patch built without Archipelago?)'
            return None
        if not state['marker']:
            self.status = 'no save of this seed loaded (title screen, or another seed)'
            return None
        self.count = state['count']
        self.waiting = max(0, len(names) - (state['count'] or 0))
        writes = self.mailbox.step(names, state, self.clock())
        if writes:
            self.game.write_bools(writes)
        index = self.mailbox.index
        if not self.waiting:
            self.status = 'every received item is in the game'
        elif state['signal']:
            self.status = f'{self.waiting} item(s) to hand over: waiting for the game to take one (menu or scene?)'
        else:
            self.status = f'{self.waiting} item(s) to hand over'
        if self.mailbox.aside_until > self.clock():
            self.status += f' (item {index + 1} not taken yet: tried again in a minute)'
        return index if writes else None


class GameMailbox:
    """Delivery's view of the running game: Bools by name over a live_memory.LiveGameData (built with
    ``writable=WRITABLE``, so nothing but the mailbox keys can be written)."""

    def __init__(self, data):
        self.data = data
        self._keys = {}

    def _key(self, name):
        key = self._keys.get(name)
        if key is None:
            key = self._keys[name] = murmur3(name)
        return key

    def read_bools(self, names):
        keys = {name: self._key(name) for name in names}
        values = self.data.read_keys(list(keys.values()))
        return {name: values.get(key) for name, key in keys.items()}

    def write_bools(self, pairs):
        self.data.write_keys([(self._key(name), value) for name, value in pairs])
