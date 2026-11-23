"""A fake Archipelago server over real sockets, for the client's tests (standard library only; test-only code).

Two layers, one thread per client:

* ``WSServer`` / ``ServerConnection``: the server side of RFC 6455 on ``client.websocket``'s frame helpers (it reads
  masked frames and sends unmasked ones), permessage-deflate (RFC 7692) when the client offers it, with or without
  context takeover, and TLS when given an ``ssl.SSLContext``. ``handler(conn)`` runs in the client's thread once the
  handshake is done; the WebSocket tests script frames with it.
* ``FakeAPServer``: one Archipelago slot on top, answering the way Archipelago's MultiServer does (RoomInfo,
  GetDataPackage, Connect, ReceivedItems, LocationChecks, Say, Sync, StatusUpdate, LocationScouts, ConnectUpdate).

    srv = FakeAPServer(slot_data={'seed': '12345'}, items=[{'item': 77, 'location': 2000, 'player': 2, 'flags': 1}])
    url = srv.start()                          # 'ws://127.0.0.1:PORT'
    ...                                        # a client connects, sends checks...
    srv.wait_for(lambda: 101 in srv.checked_locations)
    srv.stop()

A connection's socket is used only by its own thread. Other threads (``send_item``, ``broadcast``, ``drop_clients``,
``stop``) queue work that the connection picks up within ``POLL`` seconds.
"""
import base64
import binascii
import copy
import hashlib
import json
import os
import socket
import ssl
import struct
import threading
import time
import zlib
from collections import deque

from client.websocket import (DEFLATE_TAIL, MAX_HANDSHAKE, MAX_MESSAGE, OP_BINARY, OP_CLOSE, OP_CONT, OP_PING,
                              OP_PONG, OP_TEXT, FrameParser, ProtocolError, accept_key, close_payload, encode_frame,
                              parse_close, parse_extensions)

POLL = 0.02              # Check the queue and stop/drop requests this often while waiting.
IO_TIMEOUT = 5.0         # handshake, sends, and the default wait of the scripted reads
GAME = 'Rando of Time'
VERSION = {'major': 0, 'minor': 6, 'build': 6, 'class': 'Version'}


class ServerStopped(Exception):
    """The server is stopping or dropped the client: ends a handler quietly."""


class _NotHTTP(Exception):
    pass


# Handshake
def _read_request(sock):
    """(request, bytes after it) of the client's HTTP upgrade request."""
    data = bytearray()
    while b'\r\n\r\n' not in data:
        if len(data) > MAX_HANDSHAKE:
            raise _NotHTTP('request too long')
        chunk = sock.recv(4096)
        if not chunk:
            raise EOFError('the client left during the handshake')
        data += chunk
        if not (65 <= data[0] <= 90):          # 'GET ...'; a TLS ClientHello starts with 0x16
            raise _NotHTTP(f'not an HTTP request (first byte {data[0]:#04x})')
    head, _, rest = bytes(data).partition(b'\r\n\r\n')
    lines = head.decode('iso-8859-1').split('\r\n')
    parts = lines[0].split(' ')
    if len(parts) != 3:
        raise _NotHTTP(f'bad request line {lines[0]!r}')
    headers = {}
    for line in lines[1:]:
        name, colon, value = line.partition(':')
        if not colon:
            raise _NotHTTP(f'bad header line {line!r}')
        name = name.strip().lower()
        headers[name] = headers[name] + ', ' + value.strip() if name in headers else value.strip()
    return {'method': parts[0], 'path': parts[1], 'version': parts[2], 'headers': headers, 'raw': head}, rest


def upgrade_problems(request):
    """What is wrong with a client's upgrade request (RFC 6455 section 4.1), [] when nothing."""
    h, problems = request['headers'], []
    if request['method'] != 'GET' or request['version'] != 'HTTP/1.1':
        problems.append(f'request line {request["method"]} {request["version"]}')
    if not h.get('host'):
        problems.append('no Host')
    if h.get('upgrade', '').lower() != 'websocket':
        problems.append('Upgrade is not websocket')
    if 'upgrade' not in [t.strip().lower() for t in h.get('connection', '').split(',')]:
        problems.append('Connection has no upgrade token')
    if h.get('sec-websocket-version') != '13':
        problems.append('Sec-WebSocket-Version is not 13')
    try:
        if len(base64.b64decode(h.get('sec-websocket-key', ''), validate=True)) != 16:
            problems.append('Sec-WebSocket-Key is not 16 bytes')
    except (binascii.Error, ValueError):
        problems.append('Sec-WebSocket-Key is not base64')
    return problems


def accept_response(request, extensions=None, accept=None, extra=()):
    """A 101 answer to ``request``. ``accept`` is a wrong Sec-WebSocket-Accept on purpose, ``extra`` is header lines."""
    key = request['headers'].get('sec-websocket-key', '')
    lines = ['HTTP/1.1 101 Switching Protocols', 'Upgrade: websocket', 'Connection: Upgrade',
             f'Sec-WebSocket-Accept: {accept_key(key) if accept is None else accept}']
    if extensions:
        lines.append(f'Sec-WebSocket-Extensions: {extensions}')
    lines.extend(extra)
    return ('\r\n'.join(lines) + '\r\n\r\n').encode('iso-8859-1')


def _http_error(status, text):
    body = text.encode('utf-8')
    return (f'HTTP/1.1 {status}\r\nContent-Type: text/plain\r\nContent-Length: {len(body)}\r\n'
            f'Connection: close\r\n\r\n').encode('ascii') + body


# One connection
class ServerConnection:
    """The server side of one WebSocket. Its socket is used only by the client's thread (the handler's)."""

    def __init__(self, server, sock, address, request, deflate, leftover=b''):
        self.server, self.sock, self.address, self.request = server, sock, address, request
        self.deflate = deflate               # None, or {'no_context_takeover': bool} once permessage-deflate is on
        self.parser = FrameParser(masked=True, max_size=server.max_size, allow_rsv1=deflate is not None)
        self.parser.feed(leftover)
        self._compressor = None
        self._inflater = zlib.decompressobj(-15)
        self._parts = None
        self._outbox = deque()
        self._abort = None
        self.close_sent, self.close_received, self.closed = False, None, False
        self.pongs = []                      # payloads of the client's pongs
        self.sent_messages = self.sent_compressed = 0
        self.state = {}                      # free for handlers (FakeAPServer keeps the slot's login here)
        self.done = threading.Event()        # set once the handler has returned and the socket is closed

    # Sending (own thread)
    def send_raw(self, data):
        self.sock.settimeout(IO_TIMEOUT)
        self.sock.sendall(data)

    def send_frame(self, opcode, payload=b'', fin=True, rsv1=False):
        self.send_raw(encode_frame(opcode, payload, fin=fin, rsv1=rsv1))

    def compress(self, data):
        """permessage-deflate payload of one message (sync flush, ``00 00 ff ff`` removed)."""
        if self.deflate is None:
            raise ValueError('permessage-deflate was not negotiated')
        if self._compressor is None or self.deflate['no_context_takeover']:
            self._compressor = zlib.compressobj(zlib.Z_DEFAULT_COMPRESSION, zlib.DEFLATED, -15)
        out = self._compressor.compress(bytes(data)) + self._compressor.flush(zlib.Z_SYNC_FLUSH)
        assert out.endswith(DEFLATE_TAIL)
        return out[:-len(DEFLATE_TAIL)]

    def send_message(self, message, compress=True):
        """A text (str) or binary (bytes) message, compressed when permessage-deflate is on, unless ``compress`` is
        false (a server may send any message uncompressed)."""
        data = message.encode('utf-8') if isinstance(message, str) else bytes(message)
        zipped = bool(compress) and self.deflate is not None
        if zipped:
            data = self.compress(data)
        self.send_frame(OP_TEXT if isinstance(message, str) else OP_BINARY, data, rsv1=zipped)
        self.sent_messages += 1
        self.sent_compressed += zipped

    def post(self, message):
        """Queues a message from any thread; the connection's thread sends it."""
        self._outbox.append(message)

    def flush(self):
        while self._outbox and not self.closed:
            self.send_message(self._outbox.popleft())

    # Receiving (own thread)
    def _fill(self, deadline):
        """Reads more bytes; False once the connection is gone. Flushes the queue and obeys stop/drop meanwhile."""
        while True:
            self.flush()
            self._check_abort()
            now = time.monotonic()
            if deadline is not None and now >= deadline:
                raise TimeoutError('nothing from the client')
            self.sock.settimeout(POLL if deadline is None else max(0.001, min(POLL, deadline - now)))
            try:
                data = self.sock.recv(1 << 16)
            except (TimeoutError, ssl.SSLWantReadError):
                continue
            except OSError:
                data = b''
            if not data:
                self.closed = True
                return False
            self.parser.feed(data)
            return True

    def recv_frame(self, timeout=IO_TIMEOUT):
        """(fin, rsv1, opcode, payload) of the client's next frame, None once the connection is gone.
        TimeoutError after ``timeout`` s (None: no limit); ProtocolError when the client broke RFC 6455."""
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            frame = self.parser.next_frame()
            if frame is not None:
                return frame
            if self.closed or not self._fill(deadline):
                return None

    def recv_message(self, timeout=IO_TIMEOUT):
        """The client's next message (str or bytes); None once the connection ended (its close is answered)."""
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            frame = self.recv_frame(None if deadline is None else max(0.0, deadline - time.monotonic()))
            if frame is None:
                return None
            fin, rsv1, opcode, payload = frame
            if opcode == OP_PING:
                self.send_frame(OP_PONG, payload)
                continue
            if opcode == OP_PONG:
                self.pongs.append(payload)
                continue
            if opcode == OP_CLOSE:
                self.close_received = parse_close(payload)
                if not self.close_sent:
                    code = self.close_received[0]
                    self.close_sent = True
                    try:
                        self.send_frame(OP_CLOSE, b'' if code == 1005 else close_payload(code))
                    except OSError:
                        pass
                self.shutdown()
                return None
            if opcode == OP_CONT:
                if self._parts is None:
                    raise ProtocolError('continuation frame without a message')
                if rsv1:
                    raise ProtocolError('compression bit on a continuation frame')
            else:
                if self._parts is not None:
                    raise ProtocolError('new message before the last one ended')
                self._parts = (opcode, rsv1, [])
            self._parts[2].append(payload)
            if not fin:
                continue
            kind, zipped, parts = self._parts
            self._parts = None
            data = b''.join(parts)
            if zipped:                       # the client keeps its context: one inflater for the connection
                data = self._inflater.decompress(data + DEFLATE_TAIL)
            if kind == OP_TEXT:
                try:
                    return data.decode('utf-8')
                except UnicodeDecodeError:
                    raise ProtocolError('text message is not UTF-8', 1007) from None
            return data

    def wait_closed(self, timeout=IO_TIMEOUT):
        """Answers pings and the client's close until the connection ends (data messages are dropped).
        The client's (code, reason), or None."""
        deadline = time.monotonic() + timeout
        while not self.closed:
            try:
                if self.recv_message(max(0.0, deadline - time.monotonic())) is None:
                    break
            except TimeoutError:
                break
        return self.close_received

    # Closing
    def close(self, code=1000, reason='', wait=IO_TIMEOUT):
        """The server's closing handshake: our close frame, the client's answer (recorded), then TCP close."""
        if not self.closed and not self.close_sent:
            self.close_sent = True
            self.send_frame(OP_CLOSE, close_payload(code, reason))
        deadline = time.monotonic() + wait
        while not self.closed:
            try:
                frame = self.recv_frame(max(0.0, deadline - time.monotonic()))
            except TimeoutError:
                break
            if frame is None:
                break
            if frame[2] == OP_CLOSE:
                self.close_received = parse_close(frame[3])
                break
        self.shutdown()

    def fail(self, code, reason=''):
        """Close frame with ``code`` (no wait), then TCP close: what a server does when the client broke the rules."""
        if not self.closed and not self.close_sent:
            self.close_sent = True
            try:
                self.send_frame(OP_CLOSE, close_payload(code, reason))
            except OSError:
                pass
        self.shutdown()

    def shutdown(self):
        """Closes the TCP connection (FIN) without a close frame."""
        self.closed = True
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass

    def abort(self):
        """Resets the TCP connection (RST): no close frame, no FIN."""
        self.closed = True
        try:
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER,
                                 struct.pack('HH' if os.name == 'nt' else 'ii', 1, 0))
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass

    def request_abort(self, kind):
        """From another thread: 'drop' (no close frame) or 'stop' (close 1001), done by the connection's thread."""
        self._abort = kind

    def _check_abort(self):
        kind = self._abort
        if kind is None:
            return
        if kind == 'stop' and not self.closed and not self.close_sent:
            self.close_sent = True
            try:
                self.send_frame(OP_CLOSE, close_payload(1001, 'server stopping'))
            except OSError:
                pass
        self.shutdown()
        raise ServerStopped(kind)


# The server
class WSServer:
    """A WebSocket server running ``handler(conn)`` in one thread per client.

    ``respond(request) -> bytes`` gives the raw HTTP answer instead of the normal 101 (handshake tests), and
    permessage-deflate is then on when that answer mentions it. ``rcvbuf`` is SO_RCVBUF of the accepted sockets (a slow
    reader). Handler exceptions other than ServerStopped land in ``errors``, like a test script's failed check or a
    client that broke RFC 6455. That client's connection is then failed with the right close code.
    """

    def __init__(self, handler, host='127.0.0.1', port=0, ssl_context=None, compression=True,
                 no_context_takeover=False, respond=None, max_size=MAX_MESSAGE, rcvbuf=None):
        self.handler, self.host, self.port, self.ssl_context = handler, host, port, ssl_context
        self.compression, self.no_context_takeover, self.respond = compression, no_context_takeover, respond
        self.max_size, self.rcvbuf = max_size, rcvbuf
        self.connections = []                # ServerConnection, in accept order
        self.requests = []                   # every upgrade request
        self.errors = []                     # exceptions of handlers
        self.handshake_errors = []           # TLS or HTTP failures before the WebSocket started
        self.url = None
        self._lock = threading.Lock()
        self._stopping = threading.Event()
        self._listener = None
        self._threads = []

    def start(self):
        if self.url:
            return self.url
        family = socket.AF_INET6 if ':' in self.host else socket.AF_INET
        listener = socket.socket(family, socket.SOCK_STREAM)
        try:
            if self.rcvbuf:
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, self.rcvbuf)
            listener.bind((self.host, self.port))
            listener.listen(16)
        except OSError:
            listener.close()
            raise
        listener.settimeout(POLL)
        self._listener = listener
        self.port = listener.getsockname()[1]
        thread = threading.Thread(target=self._accept_loop, name='fake-ws-accept', daemon=True)
        self._threads.append(thread)
        thread.start()
        host = f'[{self.host}]' if ':' in self.host else self.host
        self.url = f'{"wss" if self.ssl_context is not None else "ws"}://{host}:{self.port}'
        return self.url

    def stop(self, timeout=2.0):
        """Stops accepting; every client gets a close 1001 and its TCP connection closed."""
        self._stopping.set()
        if self._listener is not None:
            try:
                self._listener.close()
            except OSError:
                pass
        with self._lock:
            connections = list(self.connections)
        for conn in connections:
            conn.request_abort('stop')
        end = time.monotonic() + timeout
        for thread in list(self._threads):
            if thread is not threading.current_thread():
                thread.join(max(0.0, end - time.monotonic()))

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.stop()

    def live_connections(self):
        with self._lock:
            return [c for c in self.connections if not c.done.is_set()]

    def _accept_loop(self):
        while not self._stopping.is_set():
            try:
                sock, address = self._listener.accept()
            except TimeoutError:
                continue
            except OSError:
                break
            if self._stopping.is_set():
                sock.close()
                break
            thread = threading.Thread(target=self._client, args=(sock, address), name='fake-ws-client', daemon=True)
            self._threads.append(thread)
            thread.start()

    def _client(self, sock, address):
        conn = None
        try:
            try:
                sock.settimeout(IO_TIMEOUT)
                if self.ssl_context is not None:
                    sock = self.ssl_context.wrap_socket(sock, server_side=True)
                request, leftover = _read_request(sock)
            except _NotHTTP as error:        # e.g. a wss:// client on this plain server: answer like a web server
                self.handshake_errors.append(error)
                try:
                    sock.sendall(_http_error('400 Bad Request', str(error)))
                except OSError:
                    pass
                return
            except (OSError, EOFError, ValueError) as error:
                self.handshake_errors.append(error)
                return
            self.requests.append(request)
            if self.respond is not None:
                response = self.respond(request)
                lower = response.lower()
                deflate = ({'no_context_takeover': b'server_no_context_takeover' in lower}
                           if b'permessage-deflate' in lower else None)
            else:
                problems = upgrade_problems(request)
                if problems:
                    self.handshake_errors.append(ValueError('bad upgrade request: ' + '; '.join(problems)))
                    sock.sendall(_http_error('400 Bad Request', '; '.join(problems)))
                    return
                offered = any(name == 'permessage-deflate'
                              for name, _ in parse_extensions(request['headers'].get('sec-websocket-extensions')))
                deflate, answer = None, None
                if self.compression and offered:
                    deflate = {'no_context_takeover': bool(self.no_context_takeover)}
                    answer = 'permessage-deflate' + ('; server_no_context_takeover' if self.no_context_takeover
                                                     else '')
                response = accept_response(request, answer)
            sock.sendall(response)
            conn = ServerConnection(self, sock, address, request, deflate, leftover)
            with self._lock:
                self.connections.append(conn)
            if self._stopping.is_set():
                conn.request_abort('stop')
            self.handler(conn)
        except ServerStopped:
            pass
        except ProtocolError as error:
            self.errors.append(error)
            if conn is not None:
                conn.fail(error.code, str(error))
        except Exception as error:  # noqa: BLE001 - reported through errors
            self.errors.append(error)
        finally:
            if conn is not None:
                conn.shutdown()
                conn.done.set()
            else:
                try:
                    sock.close()
                except OSError:
                    pass


# Archipelago
def _checksum(data):
    body = {k: v for k, v in data.items() if k != 'checksum'}
    return hashlib.sha1(json.dumps(body, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()


def default_datapackage(games, ids=range(1000, 1200)):
    """{game: {'item_name_to_id', 'location_name_to_id', 'checksum'}} with names like 'A Link to the Past item 1001'."""
    out = {}
    for game in games:
        data = {'item_name_to_id': {f'{game} item {i}': i for i in ids},
                'location_name_to_id': {f'{game} location {i}': i for i in ids}}
        data['checksum'] = _checksum(data)
        out[game] = data
    return out


def network_item(item, location, player, flags=0):
    return {'item': int(item), 'location': int(location), 'player': int(player), 'flags': int(flags or 0),
            'class': 'NetworkItem'}


AUTH_ONLY = {'LocationChecks', 'Say', 'Sync', 'StatusUpdate', 'LocationScouts', 'ConnectUpdate', 'Bounce', 'Get',
             'Set', 'SetNotify', 'CreateHints', 'UpdateHint'}
NO_OPS = {'Bounce', 'Get', 'Set', 'SetNotify', 'CreateHints', 'UpdateHint'}      # accepted, recorded, unanswered


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


class FakeAPServer:
    """One Archipelago slot (``slot``, ``slot_name``, ``game``) in a room with ``other_players`` {slot: (name, game)}.

    ``items`` are the NetworkItems the slot has received ({item, location, player, flags}). A client gets the ones its
    items_handling asks for (bit 0 any, bit 1 also from its own world, bit 2 also the starting inventory at location
    -2), and ReceivedItems indexes only count those, like Archipelago does. ``location_items`` is {location: (receiving
    slot, item id, flags)}, and any other location holds item ``location + 1`` for player 2 (flags 0). ``locations`` is
    the slot's location ids (Connected's missing_locations), by default its game's ids in the DataPackage.
    ``datapackage`` is {game: {item_name_to_id, location_name_to_id, checksum}}, or None for ``default_datapackage`` of
    the room's games.
    """

    def __init__(self, game=GAME, slot_name='Alice', slot=1, password=None, slot_data=None, other_players=None,
                 items=(), datapackage=None, checked=(), compression=True, no_context_takeover=False,
                 ssl_context=None, host='127.0.0.1', port=0, location_items=None, locations=None, team=0):
        self.game, self.slot_name, self.slot, self.password, self.team = game, slot_name, slot, password, team
        self.slot_data = dict(slot_data or {})
        others = {2: ('Bob', 'A Link to the Past')} if other_players is None else other_players
        self.players = {slot: (slot_name, game)}
        self.players.update({int(k): (v[0], v[1]) for k, v in others.items() if int(k) != slot})
        self.games = sorted({g for _, g in self.players.values()})
        if datapackage is None:
            self.datapackage = default_datapackage(self.games)
        else:
            self.datapackage = copy.deepcopy(datapackage)
            for data in self.datapackage.values():
                data.setdefault('checksum', _checksum(data))
        self.location_items = {int(k): tuple(v) for k, v in (location_items or {}).items()}
        if locations is None:
            locations = (self.datapackage.get(game) or {}).get('location_name_to_id', {}).values()
        self.locations = {int(i) for i in locations}
        self.lock = threading.RLock()
        self.packets = []                    # every packet from clients, in order (received_packets(): a copy)
        self._items = [network_item(i['item'], i['location'], i['player'], i.get('flags', 0)) for i in items]
        self._checked = {int(i) for i in checked}
        self._status_updates, self._said, self._dp_requests, self._ignored = [], [], [], []
        self._connects = 0
        self._goal = False
        self._ws = WSServer(self._serve, host=host, port=port, ssl_context=ssl_context, compression=compression,
                            no_context_takeover=no_context_takeover)

    # Control (any thread)
    def start(self):
        """Starts listening; the URL to connect to ('ws://127.0.0.1:PORT' or 'wss://...')."""
        return self._ws.start()

    def stop(self):
        self._ws.stop()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.stop()

    @property
    def url(self):
        return self._ws.url

    @property
    def errors(self):
        """Exceptions in client threads: a client that broke RFC 6455 or sent something unreadable."""
        return list(self._ws.errors)

    def received_packets(self):
        with self.lock:
            return [dict(p) for p in self.packets]

    @property
    def checked_locations(self):
        with self.lock:
            return set(self._checked)

    @property
    def status_updates(self):
        with self.lock:
            return list(self._status_updates)

    @property
    def said(self):
        with self.lock:
            return list(self._said)

    @property
    def connects(self):
        with self.lock:
            return self._connects

    @property
    def get_datapackage_requests(self):
        with self.lock:
            return [None if g is None else list(g) for g in self._dp_requests]

    @property
    def ignored_packets(self):
        """Packets that need a login, sent before Connected (a real server ignores them too)."""
        with self.lock:
            return list(self._ignored)

    @property
    def items(self):
        with self.lock:
            return [dict(i) for i in self._items]

    def clients(self):
        """Live connections that completed Connect."""
        return [c for c in self._ws.live_connections() if c.state.get('authed') and not c.closed]

    def send_item(self, item_id, from_player=2, location=1000, flags=1):
        """The slot receives an item: appended to its items and pushed to connected clients as ReceivedItems."""
        item = network_item(item_id, location, from_player, flags)
        with self.lock:
            self._give([item])
        return dict(item)

    def broadcast(self, *packets):
        """Any packets to every connected client (one message)."""
        with self.lock:
            self._broadcast(list(packets))

    def drop_clients(self, timeout=2.0):
        """Closes every client's TCP connection abruptly (no close frame); returns once they are closed."""
        connections = self._ws.live_connections()
        for conn in connections:
            conn.request_abort('drop')
        for conn in connections:
            conn.done.wait(timeout)

    @staticmethod
    def wait_for(predicate, timeout=5.0):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if predicate():
                return True
            time.sleep(0.01)
        return bool(predicate())

    # One client (its own thread)
    def _serve(self, conn):
        conn.state.update(authed=False, items_handling=0, tags=[])
        conn.post(self._json([self._room_info()]))
        while True:
            message = conn.recv_message(timeout=None)
            if message is None:
                return
            self._on_message(conn, message)
            conn.flush()

    def _on_message(self, conn, message):
        if isinstance(message, bytes):
            return self._invalid(conn, None, 'binary message: packets are JSON text', 'cmd')
        try:
            packets = json.loads(message)
        except ValueError:
            return self._invalid(conn, None, 'not JSON', 'cmd')
        if not isinstance(packets, list):
            return self._invalid(conn, None, 'packets come in a JSON list', 'cmd')
        handlers = {'Connect': self._connect, 'GetDataPackage': self._get_datapackage,
                    'LocationChecks': self._location_checks, 'Say': self._say, 'Sync': self._sync,
                    'StatusUpdate': self._status_update, 'LocationScouts': self._location_scouts,
                    'ConnectUpdate': self._connect_update}
        for packet in packets:
            if not isinstance(packet, dict) or not isinstance(packet.get('cmd'), str):
                self._invalid(conn, None, 'a packet is an object with a "cmd"', 'cmd')
                continue
            cmd = packet['cmd']
            with self.lock:
                self.packets.append(packet)
            if cmd not in handlers and cmd not in NO_OPS:
                self._invalid(conn, cmd, f'Unknown command "{cmd}"', 'cmd')
            elif cmd in AUTH_ONLY and not conn.state.get('authed'):
                with self.lock:
                    self._ignored.append(packet)
            elif cmd in handlers:
                handlers[cmd](conn, packet)

    # Packets
    def _room_info(self):
        return {'cmd': 'RoomInfo', 'version': dict(VERSION), 'generator_version': dict(VERSION), 'tags': ['AP'],
                'password': self.password is not None,
                'permissions': {'release': 6, 'collect': 6, 'remaining': 2}, 'hint_cost': 10,
                'location_check_points': 1, 'games': list(self.games),
                'datapackage_checksums': {g: self.datapackage[g]['checksum'] for g in self.games
                                          if g in self.datapackage and 'checksum' in self.datapackage[g]},
                'seed_name': 'fake-seed', 'time': time.time()}

    def _get_datapackage(self, conn, packet):
        games = packet.get('games')
        with self.lock:
            self._dp_requests.append(games)
        wanted = self.datapackage if games is None else [g for g in games if g in self.datapackage]
        conn.post(self._json([{'cmd': 'DataPackage', 'data': {'games': {g: self.datapackage[g] for g in wanted}}}]))

    def _connect(self, conn, packet):
        errors = []
        tags = packet.get('tags') if isinstance(packet.get('tags'), list) else []
        if self.password is not None and packet.get('password') != self.password:
            errors.append('InvalidPassword')
        if packet.get('name') != self.slot_name:
            errors.append('InvalidSlot')
        elif packet.get('game') != self.game and not (('TextOnly' in tags or 'Tracker' in tags)
                                                     and not packet.get('game')):
            errors.append('InvalidGame')
        version = packet.get('version')
        if not isinstance(version, dict) or version.get('class') != 'Version' or \
                not all(_is_int(version.get(k)) for k in ('major', 'minor', 'build')):
            errors.append('IncompatibleVersion')
        handling = packet.get('items_handling')
        if not _is_int(handling) or not 0 <= handling <= 0b111:
            errors.append('InvalidItemsHandling')
        if errors:
            conn.post(self._json([{'cmd': 'ConnectionRefused', 'errors': errors}]))
            return
        with self.lock:
            conn.state.update(authed=True, items_handling=handling, tags=list(tags))
            self._connects += 1
            connected = {
                'cmd': 'Connected', 'team': self.team, 'slot': self.slot,
                'players': [{'team': self.team, 'slot': s, 'alias': name, 'name': name, 'class': 'NetworkPlayer'}
                            for s, (name, _) in sorted(self.players.items())],
                'missing_locations': sorted(self.locations - self._checked),
                'checked_locations': sorted(self._checked),
                'slot_info': {str(s): {'name': name, 'game': game, 'type': 1, 'group_members': [],
                                       'class': 'NetworkSlot'} for s, (name, game) in sorted(self.players.items())},
                'hint_points': 0}
            if packet.get('slot_data', True):
                connected['slot_data'] = copy.deepcopy(self.slot_data)
            reply = [connected]
            items = self._view(handling)
            if items:                        # like MultiServer: no ReceivedItems while there is nothing
                reply.append({'cmd': 'ReceivedItems', 'index': 0, 'items': items})
            conn.post(self._json(reply))
            self._broadcast([{'cmd': 'PrintJSON', 'type': 'Join', 'team': self.team, 'slot': self.slot,
                              'tags': list(tags),
                              'data': [{'text': f'{self.slot_name} (Team #{self.team + 1}) playing {self.game} has '
                                                f'joined. Client({version["major"]}.{version["minor"]}.'
                                                f'{version["build"]}), {tags}.'}]}])

    def _location_checks(self, conn, packet):
        locations = packet.get('locations')
        if not isinstance(locations, list) or not all(_is_int(i) for i in locations):
            return self._invalid(conn, 'LocationChecks', 'locations is a list of ids', 'arguments')
        with self.lock:
            new = sorted(set(locations) - self._checked)
            if not new:
                return
            self._checked.update(new)
            found, own = [], []
            for location in new:
                receiving, item, flags = self._item_at(location)
                found.append((receiving, flags, item, location))
                if receiving == self.slot:
                    own.append(network_item(item, location, self.slot, flags))
            # MultiServer's order: the ItemSend texts, then ReceivedItems, then RoomUpdate.
            self._broadcast([self._item_send(item, location, receiving, flags)
                             for receiving, flags, item, location in sorted(found)])
            if own:
                self._give(own)
            for client in self.clients():
                client.post(self._json([{'cmd': 'RoomUpdate', 'checked_locations': new}]))

    def _say(self, conn, packet):
        text = packet.get('text')
        if not isinstance(text, str) or not text.isprintable():
            return self._invalid(conn, 'Say', 'text is printable text', 'arguments')
        with self.lock:
            self._said.append(text)
            self._broadcast([{'cmd': 'PrintJSON', 'type': 'Chat', 'team': self.team, 'slot': self.slot,
                              'message': text, 'data': [{'text': f'{self.slot_name}: {text}'}]}])

    def _sync(self, conn, packet):
        with self.lock:
            conn.post(self._json([{'cmd': 'ReceivedItems', 'index': 0,
                                   'items': self._view(conn.state['items_handling'])}]))

    def _status_update(self, conn, packet):
        status = packet.get('status')
        if not _is_int(status):
            return self._invalid(conn, 'StatusUpdate', 'status is an int', 'arguments')
        with self.lock:
            self._status_updates.append(status)
            if status == 30 and not self._goal:
                self._goal = True
                self._broadcast([{'cmd': 'PrintJSON', 'type': 'Goal', 'team': self.team, 'slot': self.slot,
                                  'data': [{'text': f'{self.slot_name} (Team #{self.team + 1}) has completed '
                                                    f'their goal.'}]}])

    def _location_scouts(self, conn, packet):
        locations = packet.get('locations')
        if not isinstance(locations, list) or not all(_is_int(i) for i in locations):
            return self._invalid(conn, 'LocationScouts', 'locations is a list of ids', 'arguments')
        infos = []
        for location in locations:
            receiving, item, flags = self._item_at(location)
            infos.append(network_item(item, location, receiving, flags))
        conn.post(self._json([{'cmd': 'LocationInfo', 'locations': infos}]))

    def _connect_update(self, conn, packet):
        handling = packet.get('items_handling', conn.state['items_handling'])
        if not _is_int(handling) or not 0 <= handling <= 0b111:
            return self._invalid(conn, 'ConnectUpdate', 'items_handling is 0..7', 'arguments')
        with self.lock:
            changed = handling != conn.state['items_handling']
            conn.state['items_handling'] = handling
            if isinstance(packet.get('tags'), list):
                conn.state['tags'] = list(packet['tags'])
            items = self._view(handling)
            if changed and items:
                conn.post(self._json([{'cmd': 'ReceivedItems', 'index': 0, 'items': items}]))

    # Helpers (under self.lock)
    def _item_at(self, location):
        if location in self.location_items:
            receiving, item, flags = self.location_items[location]
            return int(receiving), int(item), int(flags)
        return (2 if 2 in self.players and self.slot != 2 else self.slot), location + 1, 0

    def _item_send(self, item, location, receiving, flags):
        """PrintJSON ItemSend as MultiServer's json_format_send_event writes it."""
        finder = self.slot
        parts = [{'type': 'player_id', 'text': str(finder)}]
        if receiving == finder:
            parts += [{'text': ' found their '},
                      {'type': 'item_id', 'text': str(item), 'player': finder, 'flags': flags}]
        else:
            parts += [{'text': ' sent '}, {'type': 'item_id', 'text': str(item), 'player': receiving, 'flags': flags},
                      {'text': ' to '}, {'type': 'player_id', 'text': str(receiving)}]
        parts += [{'text': ' ('}, {'type': 'location_id', 'text': str(location), 'player': finder}, {'text': ')'}]
        return {'cmd': 'PrintJSON', 'type': 'ItemSend', 'data': parts, 'receiving': receiving,
                'item': network_item(item, location, finder, flags)}

    def _visible(self, item, handling):
        if not handling & 0b001:
            return False
        if item['location'] == -2:
            return bool(handling & 0b100)
        if item['player'] == self.slot:
            return bool(handling & 0b010)
        return True

    def _view(self, handling):
        return [dict(i) for i in self._items if self._visible(i, handling)]

    def _give(self, items):
        before = {id(c): len(self._view(c.state['items_handling'])) for c in self.clients()}
        self._items.extend(items)
        for client in self.clients():
            handling = client.state['items_handling']
            shown = [dict(i) for i in items if self._visible(i, handling)]
            if shown and id(client) in before:
                client.post(self._json([{'cmd': 'ReceivedItems', 'index': before[id(client)], 'items': shown}]))

    def _broadcast(self, packets):
        text = self._json(packets)
        for client in self.clients():
            client.post(text)

    def _invalid(self, conn, cmd, text, kind):
        packet = {'cmd': 'InvalidPacket', 'type': kind, 'text': text}
        if cmd is not None:
            packet['original_cmd'] = cmd
        conn.post(self._json([packet]))

    @staticmethod
    def _json(packets):
        return json.dumps(packets, ensure_ascii=False, separators=(',', ':'))
