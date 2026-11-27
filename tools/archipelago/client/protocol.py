# Ported from OotrR (github.com/Mozencaz/OotrR, src/oot_rando/archipelago/client.py).
# Copyright (c) 2026 Mozencaz. MIT License: see LICENSE-OotrR.txt in this folder.
# Changes for Rando of Time: our standard-library WebSocket (websocket.py) instead of the websockets
# package, the seed's ap.json (data/archipelago/CONTRACT.md), DataPackage caching by checksum, an event queue for the
# window and the command line, the sent/received item log, and a growing reconnect delay.
"""Archipelago connection of one slot (https://github.com/ArchipelagoMW/Archipelago/blob/main/docs/network%20protocol.md).

RoomInfo -> GetDataPackage + Connect -> Connected -> ReceivedItems / RoomUpdate / PrintJSON. We send LocationChecks,
StatusUpdate (playing, then the goal) and Say (chat and ! commands).

The connection runs in one thread, and ``update``, ``say`` and ``stop`` only queue work for it. Everything the window
or the command line shows comes out of ``events()`` (a list of dicts, drained) and ``summary()``.

Received items: ``received`` is the server's list in server order, and its index is the item's index. A reconnect
(or a ``Sync``) gives the whole list again from index 0 and that replaces it, so nothing is appended twice. What
reached the game is decided by the game's own write-back (delivery.py), never by this list, so a reconnect never
re-delivers.
"""
from collections import deque
import ipaddress
import json
import os
import re
import ssl
import threading
import time
import uuid

from . import websocket

DEFAULT_PORT = 38281
VERSION = {'major': 0, 'minor': 6, 'build': 9, 'class': 'Version'}   # the Archipelago the apworld targets
CLIENT_PLAYING, CLIENT_GOAL = 20, 30
RETRY_SECONDS = (5, 5, 10, 15, 30)      # reconnect delays, the last one repeats
FATAL_REFUSALS = {'InvalidSlot', 'InvalidGame', 'IncompatibleVersion', 'InvalidPassword', 'InvalidItemsHandling'}
PROGRESSION, USEFUL, TRAP = 0b001, 0b010, 0b100
SUPPORTED_MAILBOX = (1,)                # mailbox_version values this client delivers for


class ClientError(Exception):
    """Configuration that no retry can fix (wrong slot, password, seed...)."""


def server_urls(address):
    """WebSocket URLs to try for an address typed by the player (secure first, like Archipelago's own clients).

    The plain ``ws://`` one is only a fallback for a server that does not speak TLS, never after a certificate error.
    """
    address = (address or '').strip()
    if address.startswith('/connect '):
        address = address[len('/connect '):].strip()
    if not address:
        raise ClientError('Enter the server address (for example archipelago.gg:38281).')
    if '://' in address:
        if not address.startswith(('ws://', 'wss://')):
            raise ClientError('The address starts with ws:// or wss:// (or neither).')
        return [address]
    host = address
    if ':' not in host.rsplit(']', 1)[-1]:
        host = f'{host}:{DEFAULT_PORT}'
    return [f'wss://{host}', f'ws://{host}']


def is_loopback(url):
    try:
        host = websocket.split_url(url)[1]
    except ValueError:
        return False
    if host.lower() == 'localhost':
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def tls_unsupported(error):
    """Whether a failed ``wss://`` attempt means the server speaks plain WebSocket.

    A certificate that does not verify is an error of its own: falling back to an unencrypted connection then would
    hand the password to whoever answered.
    """
    if isinstance(error, ssl.SSLCertVerificationError):
        return False
    if isinstance(error, ssl.SSLError):
        return True                       # wrong version number, record layer failure...
    text = str(error).lower()
    return isinstance(error, (ConnectionResetError, EOFError)) or 'did not receive a valid http response' in text


class LocationReporter:
    """Which done locations the server still has to learn (pure: no network)."""

    def __init__(self, known=()):
        self.known = set(known)          # this slot's location ids (ap.json); others are never sent
        self.server_checked = set()
        self.sent = set()

    def reset_connection(self, checked=()):
        self.server_checked, self.sent = {int(i) for i in checked}, set()

    def pending(self, done):
        ids = {int(i) for i in done}
        if self.known:
            ids &= self.known
        return sorted(ids - self.server_checked - self.sent)

    def counts(self, done):
        """(locations the server knows done or we found, locations of this slot)."""
        mine = {int(i) for i in done} | self.server_checked
        if self.known:
            mine &= self.known
        return len(mine), len(self.known)


def render(parts, names):
    """(plain text, [(start, end, tag)]) of a PrintJSON message. ``names(kind, value, player)`` -> text."""
    out, tags, at = [], [], 0
    for part in parts or ():
        kind, text = part.get('type', 'text'), part.get('text', '')
        tag = None
        try:
            if kind == 'player_id':
                text, tag = names('player', int(text), None), 'player'
            elif kind == 'item_id':
                flags = int(part.get('flags') or 0)
                text = names('item', int(text), part.get('player'))
                tag = 'trap' if flags & TRAP else 'progression' if flags & PROGRESSION else \
                    'useful' if flags & USEFUL else 'item'
            elif kind == 'location_id':
                text, tag = names('location', int(text), part.get('player')), 'location'
            elif kind in ('player_name', 'item_name', 'location_name', 'entrance_name'):
                tag = kind.split('_')[0]
            elif kind == 'color':
                tag = None
        except (TypeError, ValueError):
            pass
        text = str(text)
        if tag:
            tags.append((at, at + len(text), tag))
        out.append(text)
        at += len(text)
    return ''.join(out), tags


def _safe(name):
    return re.sub(r'[^A-Za-z0-9_.-]+', '_', name)[:80] or 'game'


class DataPackageCache:
    """Each game's DataPackage on disk, by its checksum, so a reconnect (or the next session) only asks for the new
    ones."""

    def __init__(self, folder):
        self.folder = folder

    def path(self, game, checksum):
        return os.path.join(self.folder, f'{_safe(game)}_{_safe(checksum)}.json') if self.folder and checksum else None

    def load(self, game, checksum):
        path = self.path(game, checksum)
        if not path:
            return None
        try:
            with open(path, encoding='utf-8') as stream:
                data = json.load(stream)
            return data if isinstance(data, dict) and data.get('checksum', checksum) == checksum else None
        except (OSError, ValueError):
            return None

    def save(self, game, data):
        path = self.path(game, data.get('checksum'))
        if not path:
            return
        try:
            os.makedirs(self.folder, exist_ok=True)
            tmp = path + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as stream:
                json.dump(data, stream, ensure_ascii=False)
            os.replace(tmp, path)
        except OSError:
            pass


class APClient:
    """One connection to one slot.

    ``game`` and ``slot_name`` are what Connect sends. ``seed`` is ap.json "seed" (our generator's), compared with
    slot_data["seed"]. ``locations`` is this slot's location ids, and ``location_names`` is {id: name} of our own
    locations, shown before the DataPackage arrives. ``connect`` is websocket.connect (tests pass their own).
    """

    def __init__(self, game, slot_name, address, password='', items_handling=0b101, seed=None,
                 mailbox_version=None, locations=(), location_names=None, cache_dir=None, connect=None,
                 on_change=None, version=None):
        if not slot_name:
            raise ClientError('Enter the slot name (your player name in the multiworld).')
        self.game, self.slot_name = game, slot_name
        self.urls = server_urls(address)
        self.password = password or None
        self.items_handling, self.seed, self.mailbox_version = items_handling, seed, mailbox_version
        self.version = dict(VERSION, **(version or {}))
        self.reporter = LocationReporter(locations)
        self.own_location_names = dict(location_names or {})
        self.cache = DataPackageCache(cache_dir)
        self._connect = connect or websocket.connect
        self.on_change = on_change or (lambda: None)
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread = None
        self._outbox = deque()
        self._socket = None
        self._done, self._goal, self._goal_sent = set(), False, False
        self.uuid = uuid.uuid4().hex
        self.status, self.connected, self.fatal, self.encrypted = 'Not connected', False, False, None
        self._events = deque(maxlen=5000)
        self.received = []               # NetworkItem dicts, server order
        self.slot, self.team, self.players, self.slot_info, self.slot_data = None, None, {}, {}, {}
        self.names = {}                  # game -> {'item': {id: name}, 'location': {id: name}}
        self.room = {}
        self.hint_points = None
        self.failures = 0

    # Public
    def start(self):
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name='archipelago', daemon=True)
            self._thread.start()

    def stop(self, wait=3.0):
        """The network thread sees it within 0.25 s and closes the connection itself (one thread per socket)."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=wait)

    def update(self, done_locations, goal=False):
        """The latest done location ids and goal flag; sent at the next network turn."""
        with self._lock:
            self._done = {int(i) for i in done_locations}
            self._goal = self._goal or bool(goal)

    def say(self, text):
        """Chat message or server command (``!hint``, ``!release``, ``!collect``...)."""
        text = (text or '').strip()
        if text:
            with self._lock:
                self._outbox.append({'cmd': 'Say', 'text': text})

    def events(self):
        """What happened since the last call: dicts with 'kind' (status, log, chat, received, sent, error)."""
        with self._lock:
            out = list(self._events)
            self._events.clear()
        return out

    def summary(self):
        with self._lock:
            found, total = self.reporter.counts(self._done)
            return {'status': self.status, 'connected': self.connected, 'fatal': self.fatal,
                    'encrypted': self.encrypted, 'checks': found, 'total': total, 'received': len(self.received),
                    'goal_sent': self._goal_sent, 'slot': self.slot, 'team': self.team,
                    'hint_points': self.hint_points, 'seed_name': self.room.get('seed_name')}

    def received_items(self):
        with self._lock:
            return list(self.received)

    def item_name(self, item, player=None):
        return self.name('item', item, self.slot if player is None else player)

    def name(self, kind, value, player):
        """A player's, item's or location's name (``player``: whose game the item or location belongs to)."""
        with self._lock:
            if kind == 'player':
                if value == 0:
                    return 'Archipelago'
                return str(self.players.get(value) or (self.slot_info.get(value) or {}).get('name')
                           or f'Player {value}')
            game = (self.slot_info.get(player) or {}).get('game') if player is not None else None
            game = game or self.game
            table = (self.names.get(game) or {}).get(kind) or {}
            found = table.get(value)
            if found is None and kind == 'location' and game == self.game:
                found = self.own_location_names.get(value)
            return found or f'{kind} {value}'

    def describe_received(self, entry):
        """(item name, from whom, where) of a NetworkItem we received."""
        sender, location = entry.get('player'), entry.get('location')
        where = ('starting inventory' if location == -2 else 'sent by the server' if location == -1
                 else self.name('location', location, sender))
        return self.item_name(entry.get('item')), self.name('player', sender, None), where

    # Network
    def _run(self):
        while not self._stop.is_set():
            try:
                self._session()
            except ClientError as error:
                self._set_status(str(error), connected=False, fatal=True, kind='error')
                return
            except Exception as error:  # noqa: BLE001 - network errors: retry
                if self._stop.is_set():
                    break
                delay = RETRY_SECONDS[min(self.failures, len(RETRY_SECONDS) - 1)]   # reset by Connected
                self.failures += 1
                self._set_status(f'Disconnected ({error}); retrying in {delay} s', connected=False, kind='error')
                if self._stop.wait(delay):
                    break
                continue
            if self._stop.wait(RETRY_SECONDS[0]):
                break
        self._set_status('Disconnected', connected=False)

    def _open(self):
        first = self.urls[0]
        secure = first.startswith('wss://')
        try:
            self._set_status('Connecting to ' + first + '...')
            sock = self._connect(first, timeout=10)
            self.encrypted = secure
            return sock
        except Exception as error:  # noqa: BLE001 - the plain fallback, if any, decides
            if len(self.urls) < 2 or not tls_unsupported(error):
                if isinstance(error, ssl.SSLCertVerificationError):
                    raise ClientError("The server's certificate is not valid: connection stopped so that nothing "
                                      'is sent unencrypted. Type ws://address to connect without encryption '
                                      'anyway.') from error
                raise
        if self.password and not is_loopback(self.urls[1]):
            # A server that doesn't speak TLS only gets the password when that's asked for explicitly, because an
            # attacker on the network could have broken the secure attempt on purpose.
            raise ClientError('This server does not support encryption: the password would be sent unencrypted. '
                              'Type ws://' + self.urls[1][len('ws://'):] + ' to connect anyway.')
        self._set_status('Connecting to ' + self.urls[1] + ' (not encrypted)...')
        sock = self._connect(self.urls[1], timeout=10)
        self.encrypted = False
        return sock

    def _session(self):
        sock = self._open()
        self._socket = sock
        try:
            with self._lock:
                self.reporter.reset_connection()
                self._goal_sent = False
            while not self._stop.is_set():
                self._flush(sock)
                try:
                    raw = sock.recv(timeout=0.25)
                except TimeoutError:
                    continue
                try:
                    packets = json.loads(raw)
                except ValueError:
                    self._event('error', 'The server sent something that is not JSON: ignored.')
                    continue
                for packet in packets if isinstance(packets, list) else [packets]:
                    if isinstance(packet, dict):
                        self._handle(sock, packet)
        finally:
            self._socket = None
            try:
                sock.close(wait=0.5)
            except Exception:  # noqa: BLE001
                pass
            with self._lock:
                self.connected = False

    def _send(self, sock, *packets):
        sock.send(json.dumps(list(packets), ensure_ascii=False, separators=(',', ':')))

    def _flush(self, sock):
        packets, sent_now = [], []
        with self._lock:
            while self._outbox:
                packets.append(self._outbox.popleft())
            if self.connected:
                pending = self.reporter.pending(self._done)
                if pending:
                    packets.append({'cmd': 'LocationChecks', 'locations': pending})
                    self.reporter.sent.update(pending)
                    sent_now = pending
                if self._goal and not self._goal_sent:
                    packets.append({'cmd': 'StatusUpdate', 'status': CLIENT_GOAL})
                    self._goal_sent = True
                    self._event('goal', 'Goal reached: sent to the server.')
        if packets:
            self._send(sock, *packets)
            if sent_now:
                self._event('checks', f'Sent {len(sent_now)} check(s).', locations=sent_now)
            self.on_change()

    def _handle(self, sock, packet):
        cmd = packet.get('cmd')
        if cmd == 'RoomInfo':
            with self._lock:
                self.room = packet
            games = set(packet.get('games') or []) | {self.game}
            checksums = packet.get('datapackage_checksums') or {}
            wanted = []
            for game in sorted(games):
                cached = self.cache.load(game, checksums.get(game))
                if cached is not None:
                    self._learn(game, cached)
                else:
                    wanted.append(game)
            packets = []
            if wanted:
                packets.append({'cmd': 'GetDataPackage', 'games': wanted})
            packets.append({'cmd': 'Connect', 'password': self.password, 'game': self.game, 'name': self.slot_name,
                            'uuid': self.uuid, 'version': self.version, 'items_handling': self.items_handling,
                            'tags': [], 'slot_data': True})
            self._send(sock, *packets)
            self._set_status(f'Room found ({packet.get("seed_name") or "?"}), joining as {self.slot_name}...')
        elif cmd == 'ConnectionRefused':
            errors = [str(e) for e in packet.get('errors') or ['refused']]
            message = 'Connection refused: ' + ', '.join(errors) + self._refusal_hint(errors)
            if FATAL_REFUSALS & set(errors):
                raise ClientError(message)
            raise ConnectionError(message)
        elif cmd == 'Connected':
            slot_data = packet.get('slot_data') or {}
            theirs = slot_data.get('seed')
            if self.seed and theirs is not None and str(theirs) != str(self.seed):
                raise ClientError('This slot belongs to another seed: build and install the patch of this slot '
                                  '(its .aprr), then open that seed here.')
            mailbox = slot_data.get('mailbox_version', self.mailbox_version)
            if mailbox is not None and int(mailbox) not in SUPPORTED_MAILBOX:
                raise ClientError(f'This seed uses item-delivery version {mailbox}; this client knows '
                                  f'{", ".join(map(str, SUPPORTED_MAILBOX))}. Update the randomizer.')
            with self._lock:
                self.slot, self.team = packet.get('slot'), packet.get('team')
                self.players = {p['slot']: p.get('alias') or p.get('name') for p in packet.get('players') or ()
                                if p.get('team') == self.team}
                self.slot_info = {int(k): v for k, v in (packet.get('slot_info') or {}).items()}
                self.slot_data = slot_data
                self.hint_points = packet.get('hint_points')
                self.reporter.reset_connection(packet.get('checked_locations') or [])
                self.received = []
                self.connected = True
                self.failures = 0
                goal = self._goal
            self._send(sock, {'cmd': 'StatusUpdate', 'status': CLIENT_GOAL if goal else CLIENT_PLAYING})
            with self._lock:
                self._goal_sent = goal
            self._set_status(f'Connected as {self.slot_name}' + ('' if self.encrypted else ' (not encrypted)'),
                             connected=True)
        elif cmd == 'ReceivedItems':
            index, items = int(packet.get('index', 0)), packet.get('items') or []
            with self._lock:
                if index == 0:
                    self.received = []
                resync = index != len(self.received)
                if not resync:
                    start = len(self.received)
                    self.received.extend(items)
            if resync:
                self._send(sock, {'cmd': 'Sync'})
                return
            for offset, item in enumerate(items):
                name, sender, where = self.describe_received(item)
                self._event('received', f'{name} from {sender} ({where})', index=start + offset, item=item,
                            flags=int(item.get('flags') or 0), replay=index == 0)
            self.on_change()
        elif cmd == 'RoomUpdate':
            with self._lock:
                self.reporter.server_checked.update(int(i) for i in packet.get('checked_locations') or ())
                for p in packet.get('players') or ():
                    if p.get('team') == self.team:
                        self.players[p['slot']] = p.get('alias') or p.get('name')
                if 'hint_points' in packet:
                    self.hint_points = packet['hint_points']
            self.on_change()
        elif cmd == 'DataPackage':
            games = (packet.get('data') or {}).get('games') or {}
            for game, data in games.items():
                if isinstance(data, dict):
                    self._learn(game, data)
                    self.cache.save(game, data)
            self.on_change()
        elif cmd == 'PrintJSON':
            self._print(packet)
        elif cmd == 'InvalidPacket':
            self._event('error', 'The server rejected a packet: ' + str(packet.get('text', '')))
        elif cmd in ('Bounced', 'Retrieved', 'SetReply', 'LocationInfo'):
            pass                         # TODO: DeathLink and data storage, not used yet

    def _learn(self, game, data):
        with self._lock:
            self.names[game] = {
                'item': {int(v): k for k, v in (data.get('item_name_to_id') or {}).items()},
                'location': {int(v): k for k, v in (data.get('location_name_to_id') or {}).items()}}

    def _print(self, packet):
        text, tags = render(packet.get('data'), self.name)
        if not text:
            return
        kind = packet.get('type') or 'text'
        item = packet.get('item') or {}
        receiving = packet.get('receiving')
        with self._lock:
            me = self.slot
        if kind in ('ItemSend', 'ItemCheat') and me is not None:
            if item.get('player') == me and receiving != me:
                self._event('sent', text, tags=tags, item=item, receiving=receiving)
                return
            if receiving == me and item.get('player') == me:
                self._event('own', text, tags=tags, item=item)   # found in our own world: the seed gave it
                return
            if receiving == me:
                self._event('chat', text, tags=tags, type=kind)  # the ReceivedItems entry logs it too
                return
        self._event('chat', text, tags=tags, type=kind)

    # Helpers
    @staticmethod
    def _refusal_hint(errors):
        if 'InvalidSlot' in errors:
            return ' (no slot of that name in this room: check the slot name)'
        if 'InvalidGame' in errors:
            return ' (that slot plays another game)'
        if 'InvalidPassword' in errors:
            return ' (wrong or missing password)'
        if 'IncompatibleVersion' in errors:
            return ' (the server needs a newer client)'
        return ''

    def _event(self, kind, text, **extra):
        with self._lock:
            self._events.append(dict(extra, kind=kind, text=text, time=time.time()))
        self.on_change()

    def _set_status(self, text, connected=None, fatal=None, kind='status'):
        with self._lock:
            self.status = text
            if connected is not None:
                self.connected = connected
            if fatal is not None:
                self.fatal = fatal
        self._event(kind, text)
