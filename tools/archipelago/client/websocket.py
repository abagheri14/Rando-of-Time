"""A small WebSocket client (RFC 6455), standard library only: ``socket``, ``ssl``, ``base64``, ``struct``, ``zlib``.

Enough for an Archipelago server: ``ws://`` and ``wss://`` (TLS with the system's certificates, verified), text and
binary messages, fragmentation, ping/pong, the closing handshake, and permessage-deflate (RFC 7692) for the server's
messages (a big multiworld's DataPackage shrinks about tenfold). Our own messages go uncompressed, which the RFC allows.

    ws = connect('wss://archipelago.gg:38281', timeout=10)
    ws.send('[{"cmd": "GetDataPackage"}]')
    text = ws.recv(timeout=0.25)        # TimeoutError when nothing came; ConnectionClosed once closed
    ws.close()

Only one thread at a time calls ``recv`` and ``send`` (the AP client's network thread does both), and the socket's
single timeout gets set before each read and each write.
The frame helpers (``encode_frame``, ``FrameParser``, ``accept_key``) also serve the tests' fake server.
"""
import base64
import hashlib
import os
import socket
import ssl
import struct
import threading
import time
import zlib
from urllib.parse import urlsplit

GUID = b'258EAFA5-E914-47DA-95CA-C5AB0DC85B11'
OP_CONT, OP_TEXT, OP_BINARY, OP_CLOSE, OP_PING, OP_PONG = 0x0, 0x1, 0x2, 0x8, 0x9, 0xA
DATA_OPCODES = (OP_CONT, OP_TEXT, OP_BINARY)
CONTROL_OPCODES = (OP_CLOSE, OP_PING, OP_PONG)
SEND_TIMEOUT = 30.0     # a send waits this long for a slow peer, whatever timeout the last recv used
HISTORY = 1 << 15       # the deflate window: what a message after a BFINAL block may still refer to
# Largest message we accept. A big multiworld's DataPackage is a few tens of MB, but a server mustn't be able to
# exhaust the memory (OotrR's client keeps the same cap).
MAX_MESSAGE = 128 << 20
MAX_HANDSHAKE = 64 << 10
DEFLATE_TAIL = b'\x00\x00\xff\xff'

# CA bundles of the usual Linux distributions, only tried when this Python's OpenSSL finds none of its own. OotrR's
# Linux build once rejected every certificate (its issue #32). Verification itself is never turned off.
CA_FILES = ('/etc/ssl/certs/ca-certificates.crt',      # Debian, Ubuntu, Arch, SteamOS
            '/etc/pki/tls/certs/ca-bundle.crt',         # Fedora, RHEL
            '/etc/ssl/ca-bundle.pem',                   # openSUSE
            '/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem',
            '/etc/ssl/cert.pem')                        # Alpine, macOS
CA_DIRS = ('/etc/ssl/certs', '/etc/pki/tls/certs')


class WebSocketError(Exception):
    """Anything that ends a connection."""


class HandshakeError(WebSocketError):
    """The server did not accept the WebSocket upgrade (not a WebSocket server, wrong path...)."""


class ProtocolError(WebSocketError):
    """The peer broke RFC 6455; ``code`` is the close code we answer with."""

    def __init__(self, message, code=1002):
        super().__init__(message)
        self.code = code


class ConnectionClosed(WebSocketError):
    def __init__(self, code=1006, reason=''):
        super().__init__(f'connection closed ({code}{": " + reason if reason else ""})')
        self.code, self.reason = code, reason


# Pure helpers
def accept_key(key):
    """Sec-WebSocket-Accept for a Sec-WebSocket-Key (RFC 6455 section 4.2.2)."""
    if isinstance(key, str):
        key = key.encode('ascii')
    return base64.b64encode(hashlib.sha1(key.strip() + GUID).digest()).decode('ascii')


def apply_mask(data, mask):
    """XOR ``data`` with the 4-byte ``mask`` repeated (its own inverse)."""
    if not data:
        return b''
    count = len(data)
    pad = (mask * (count // 4 + 1))[:count]
    return (int.from_bytes(data, 'little') ^ int.from_bytes(pad, 'little')).to_bytes(count, 'little')


def encode_frame(opcode, payload=b'', fin=True, mask=None, rsv1=False):
    """One frame. ``mask``: 4 bytes (a client must mask every frame) or None (a server never masks)."""
    if isinstance(payload, str):
        payload = payload.encode('utf-8')
    head = bytearray([(0x80 if fin else 0) | (0x40 if rsv1 else 0) | (opcode & 0x0F)])
    flag = 0x80 if mask is not None else 0
    size = len(payload)
    if size < 126:
        head.append(flag | size)
    elif size < 1 << 16:
        head.append(flag | 126)
        head += struct.pack('>H', size)
    else:
        head.append(flag | 127)
        head += struct.pack('>Q', size)
    if mask is not None:
        if len(mask) != 4:
            raise ValueError('the mask is 4 bytes')
        head += mask
        payload = apply_mask(payload, mask)
    return bytes(head) + payload


def close_payload(code, reason=''):
    """A close frame's payload: the code and up to 123 bytes of reason, never cut inside a character."""
    data = reason.encode('utf-8')
    if len(data) > 123:
        data = data[:123].decode('utf-8', 'ignore').encode('utf-8')
    return struct.pack('>H', code) + data


def parse_close(payload):
    """(code, reason) of a close frame's payload."""
    if not payload:
        return 1005, ''
    if len(payload) == 1:
        raise ProtocolError('close frame of 1 byte')
    code = struct.unpack('>H', payload[:2])[0]
    if code < 1000 or code in (1004, 1005, 1006, 1015) or 1016 <= code < 3000 or code >= 5000:
        raise ProtocolError(f'invalid close code {code}')
    try:
        reason = payload[2:].decode('utf-8')
    except UnicodeDecodeError:
        raise ProtocolError('close reason is not UTF-8', 1007) from None
    return code, reason


class FrameParser:
    """Frames out of a byte stream. ``masked``: whether the peer must mask (a server reads masked client frames)."""

    def __init__(self, masked=False, max_size=MAX_MESSAGE, allow_rsv1=False):
        self.masked, self.max_size, self.allow_rsv1 = masked, max_size, allow_rsv1
        self.buffer = bytearray()

    def feed(self, data):
        self.buffer += data

    def next_frame(self):
        """(fin, rsv1, opcode, payload) of the next whole frame, or None until more bytes come."""
        buf = self.buffer
        if len(buf) < 2:
            return None
        first, second = buf[0], buf[1]
        fin, rsv1, opcode = bool(first & 0x80), bool(first & 0x40), first & 0x0F
        if first & 0x30 or (rsv1 and not self.allow_rsv1):
            raise ProtocolError('reserved bits set without an extension')
        if opcode not in DATA_OPCODES + CONTROL_OPCODES:
            raise ProtocolError(f'unknown opcode {opcode:#x}')
        masked, size = bool(second & 0x80), second & 0x7F
        if masked != self.masked:
            raise ProtocolError('masked frame from a server' if masked else 'unmasked frame from a client')
        at = 2
        if size == 126:
            if len(buf) < 4:
                return None
            size = struct.unpack_from('>H', buf, 2)[0]
            at = 4
        elif size == 127:
            if len(buf) < 10:
                return None
            size = struct.unpack_from('>Q', buf, 2)[0]
            if size >> 63:
                raise ProtocolError('frame length with the top bit set')
            at = 10
        if opcode in CONTROL_OPCODES:
            if not fin:
                raise ProtocolError('fragmented control frame')
            if size > 125:
                raise ProtocolError('control frame longer than 125 bytes')
            if rsv1:
                raise ProtocolError('compressed control frame')
        if size > self.max_size:
            raise ProtocolError(f'frame of {size} bytes is over the {self.max_size}-byte limit', 1009)
        mask = None
        if masked:
            if len(buf) < at + 4:
                return None
            mask = bytes(buf[at:at + 4])
            at += 4
        if len(buf) < at + size:
            return None
        payload = bytes(buf[at:at + size])
        del buf[:at + size]
        if mask is not None:
            payload = apply_mask(payload, mask)
        return fin, rsv1, opcode, payload


def parse_extensions(header):
    """[(name, {param: value or None})] of a Sec-WebSocket-Extensions header."""
    result = []
    for item in (header or '').split(','):
        parts = [p.strip() for p in item.split(';') if p.strip()]
        if not parts:
            continue
        params = {}
        for part in parts[1:]:
            name, eq, value = part.partition('=')
            params[name.strip().lower()] = value.strip().strip('"') if eq else None
        result.append((parts[0].lower(), params))
    return result


def deflate_settings(header):
    """{'server_no_context_takeover': bool} when the server accepted permessage-deflate, else None."""
    entries = parse_extensions(header)
    offered = [name for name, _ in entries if name != 'permessage-deflate']
    if offered or (header and header.strip() and not entries):
        raise HandshakeError(f'the server answered with an extension we did not offer: {header}')
    accepted = [params for _, params in entries]
    if not accepted:
        return None
    if len(accepted) > 1:
        raise HandshakeError('permessage-deflate accepted twice')
    params = accepted[0]
    known = {'server_no_context_takeover', 'client_no_context_takeover', 'server_max_window_bits',
             'client_max_window_bits'}
    if set(params) - known:
        raise HandshakeError(f'unknown permessage-deflate parameter: {sorted(set(params) - known)}')
    for name in ('server_max_window_bits', 'client_max_window_bits'):
        value = params.get(name)
        if value is not None and not (value.isdigit() and 8 <= int(value) <= 15):
            raise HandshakeError(f'bad {name}: {value}')
    return {'server_no_context_takeover': 'server_no_context_takeover' in params}


def parse_response(raw):
    """(status code, {lower-case header: value}) of the server's HTTP answer."""
    try:
        text = raw.decode('iso-8859-1')
    except UnicodeDecodeError:  # pragma: no cover - latin-1 decodes anything
        raise HandshakeError('unreadable answer') from None
    lines = text.split('\r\n')
    status = lines[0].split(' ', 2)
    if len(status) < 2 or not status[0].startswith('HTTP/') or not status[1].isdigit():
        raise HandshakeError('did not receive a valid HTTP response')
    headers = {}
    for line in lines[1:]:
        if not line:
            continue
        name, colon, value = line.partition(':')
        if not colon:
            raise HandshakeError('did not receive a valid HTTP response')
        name = name.strip().lower()
        headers[name] = (headers[name] + ', ' + value.strip()) if name in headers else value.strip()
    return int(status[1]), headers


# TLS
def tls_context():
    """A verifying TLS context with the system's CA certificates (also on a Linux whose OpenSSL paths are empty)."""
    context = ssl.create_default_context()
    if os.name == 'nt':
        return context  # create_default_context loads the Windows certificate stores
    paths = ssl.get_default_verify_paths()
    have = bool(paths.cafile and os.path.isfile(paths.cafile))
    if not have and paths.capath and os.path.isdir(paths.capath):
        try:
            have = any(name.endswith(('.0', '.pem', '.crt')) for name in os.listdir(paths.capath))
        except OSError:
            have = False
    if not have and not context.cert_store_stats().get('x509_ca'):
        for path in CA_FILES:
            if os.path.isfile(path):
                try:
                    context.load_verify_locations(cafile=path)
                    return context
                except (ssl.SSLError, OSError):
                    continue
        for path in CA_DIRS:
            if os.path.isdir(path):
                try:
                    context.load_verify_locations(capath=path)
                    return context
                except (ssl.SSLError, OSError):
                    continue
    return context


# The client
def split_url(url):
    """(secure, host, port, path) of a ws:// or wss:// URL."""
    parts = urlsplit(url)
    if parts.scheme not in ('ws', 'wss'):
        raise ValueError(f'not a WebSocket URL: {url}')
    if not parts.hostname:
        raise ValueError(f'no host in {url}')
    secure = parts.scheme == 'wss'
    try:
        port = parts.port or (443 if secure else 80)
    except ValueError:
        raise ValueError(f'bad port in {url}') from None
    path = (parts.path or '/') + (('?' + parts.query) if parts.query else '')
    return secure, parts.hostname, port, path


def connect(url, timeout=10.0, ssl_context=None, max_size=MAX_MESSAGE, compression=True, sock=None):
    """Opens a WebSocket. ``sock``: an already connected socket (tests); otherwise one is made."""
    secure, host, port, path = split_url(url)
    deadline = time.monotonic() + timeout
    # An ASCII host goes as bytes: str hosts are encoded with the 'idna' codec, which needs unicodedata.pyd, and that
    # DLL fails to load from a folder whose path is very long ("The filename or extension is too long").
    wire_host = host.encode('ascii') if host.isascii() else host
    raw = sock or socket.create_connection((wire_host, port), timeout=timeout)
    try:
        raw.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    except OSError:
        pass
    try:
        if secure:
            context = ssl_context or tls_context()
            raw.settimeout(max(0.1, deadline - time.monotonic()))
            raw = context.wrap_socket(raw, server_hostname=wire_host)
        key = base64.b64encode(os.urandom(16)).decode('ascii')
        host_header = f'[{host}]' if ':' in host else host
        if (secure and port != 443) or (not secure and port != 80):
            host_header += f':{port}'
        request = [f'GET {path} HTTP/1.1', f'Host: {host_header}', 'Upgrade: websocket', 'Connection: Upgrade',
                   f'Sec-WebSocket-Key: {key}', 'Sec-WebSocket-Version: 13',
                   'User-Agent: Rando-of-Time-AP-client']
        if compression:
            request.append('Sec-WebSocket-Extensions: permessage-deflate; client_max_window_bits')
        raw.settimeout(max(0.1, deadline - time.monotonic()))
        raw.sendall(('\r\n'.join(request) + '\r\n\r\n').encode('ascii'))
        answer = bytearray()
        while b'\r\n\r\n' not in answer:
            if len(answer) > MAX_HANDSHAKE:
                raise HandshakeError('handshake answer too long')
            raw.settimeout(max(0.1, deadline - time.monotonic()))
            chunk = raw.recv(4096)
            if not chunk:
                raise HandshakeError('did not receive a valid HTTP response (connection closed)')
            answer += chunk
        head, _, rest = bytes(answer).partition(b'\r\n\r\n')
        status, headers = parse_response(head)
        if status != 101:
            raise HandshakeError(f'the server refused the WebSocket upgrade (HTTP {status})')
        if headers.get('upgrade', '').lower() != 'websocket' or \
                'upgrade' not in [t.strip().lower() for t in headers.get('connection', '').split(',')]:
            raise HandshakeError('the server did not switch to WebSocket')
        if headers.get('sec-websocket-accept') != accept_key(key):
            raise HandshakeError('wrong Sec-WebSocket-Accept')
        extensions = headers.get('sec-websocket-extensions')
        if extensions and not compression:
            raise HandshakeError(f'the server answered with an extension we did not offer: {extensions}')
        deflate = deflate_settings(extensions)
        return WebSocket(raw, max_size=max_size, deflate=deflate, leftover=rest, secure=secure)
    except BaseException:
        try:
            raw.close()
        except OSError:
            pass
        raise


class WebSocket:
    def __init__(self, sock, max_size=MAX_MESSAGE, deflate=None, leftover=b'', secure=False):
        self.sock, self.max_size, self.deflate, self.secure = sock, max_size, deflate, secure
        self.parser = FrameParser(masked=False, max_size=max_size, allow_rsv1=deflate is not None)
        self.parser.feed(leftover)
        self._inflater = zlib.decompressobj(-15) if deflate else None
        self._history = b''
        self._parts, self._part_op, self._part_zipped, self._part_size = None, None, False, 0
        self._send_lock = threading.Lock()
        self.closed, self.close_code, self.close_reason = False, None, ''
        self._close_sent = False

    # Sending
    def _write(self, opcode, payload, fin=True):
        with self._send_lock:
            if self._close_sent and opcode != OP_CLOSE:
                raise ConnectionClosed(self.close_code or 1006, 'closing')
            try:
                self.sock.settimeout(SEND_TIMEOUT)   # recv leaves its own (short) deadline on the socket
                self.sock.sendall(encode_frame(opcode, payload, fin=fin, mask=os.urandom(4)))
            except OSError as error:
                self._shutdown()
                raise ConnectionClosed(1006, str(error)) from error

    def send(self, message):
        """A text message (str) or a binary one (bytes)."""
        if self.closed:
            raise ConnectionClosed(self.close_code or 1006, self.close_reason)
        if isinstance(message, str):
            self._write(OP_TEXT, message.encode('utf-8'))
        else:
            self._write(OP_BINARY, bytes(message))

    def ping(self, payload=b''):
        if len(payload) > 125:
            raise ValueError('a ping carries at most 125 bytes (RFC 6455 section 5.5)')
        self._write(OP_PING, payload)

    # Receiving
    def recv(self, timeout=None):
        """The next message (str or bytes). TimeoutError when none came in ``timeout`` seconds; ConnectionClosed."""
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            try:
                frame = self.parser.next_frame()
                if frame is None:
                    self._fill(deadline)
                    continue
                message = self._on_frame(*frame)
            except ProtocolError as error:
                self._fail(error.code, str(error))
                raise
            if message is not None:
                return message

    def _fill(self, deadline):
        if self.closed:
            raise ConnectionClosed(self.close_code or 1006, self.close_reason)
        if deadline is None:
            self.sock.settimeout(None)
        else:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('no message')
            self.sock.settimeout(remaining)
        try:
            data = self.sock.recv(1 << 16)
        except (socket.timeout, ssl.SSLWantReadError):
            raise TimeoutError('no message') from None
        except OSError as error:
            self._shutdown()
            raise ConnectionClosed(1006, str(error)) from error
        if not data:
            self._shutdown()
            raise ConnectionClosed(self.close_code or 1006, 'the connection was lost')
        self.parser.feed(data)

    def _on_frame(self, fin, rsv1, opcode, payload):
        if opcode == OP_PING:
            self._write(OP_PONG, payload)
            return None
        if opcode == OP_PONG:
            return None
        if opcode == OP_CLOSE:
            code, reason = parse_close(payload)
            self.close_code, self.close_reason = code, reason
            if not self._close_sent:
                try:
                    self._write(OP_CLOSE, close_payload(1000 if code == 1005 else code))
                except ConnectionClosed:
                    pass
                self._close_sent = True
            self._shutdown()
            raise ConnectionClosed(code, reason)
        if opcode == OP_CONT:
            if self._parts is None:
                raise ProtocolError('continuation frame without a message')
            if rsv1:
                raise ProtocolError('compression bit on a continuation frame')
        else:
            if self._parts is not None:
                raise ProtocolError('new message before the last one ended')
            self._parts, self._part_op, self._part_zipped, self._part_size = [], opcode, rsv1, 0
        self._part_size += len(payload)
        if self._part_size > self.max_size:
            raise ProtocolError(f'message over the {self.max_size}-byte limit', 1009)
        self._parts.append(payload)
        if not fin:
            return None
        data, kind, zipped = b''.join(self._parts), self._part_op, self._part_zipped
        self._parts, self._part_op, self._part_zipped, self._part_size = None, None, False, 0
        if zipped:
            data = self._inflate(data)
        if kind == OP_TEXT:
            try:
                return data.decode('utf-8')
            except UnicodeDecodeError:
                raise ProtocolError('text message is not UTF-8', 1007) from None
        return data

    def _inflate(self, data):
        takeover = not self.deflate.get('server_no_context_takeover')
        if not takeover:
            self._inflater = zlib.decompressobj(-15)
        elif self._inflater.eof:
            # The last message ended with a BFINAL block (RFC 7692 section 7.2.3.4), so a new deflate stream starts.
            # It can still refer back into the window the earlier messages filled.
            self._inflater = zlib.decompressobj(-15, zdict=self._history) if self._history else zlib.decompressobj(-15)
        try:
            out = self._inflater.decompress(data + DEFLATE_TAIL, self.max_size + 1)
        except zlib.error as error:
            raise ProtocolError(f'bad compressed data: {error}', 1007) from None
        if len(out) > self.max_size or self._inflater.unconsumed_tail:
            raise ProtocolError(f'message over the {self.max_size}-byte limit', 1009)
        if takeover:
            self._history = out[-HISTORY:] if len(out) >= HISTORY else (self._history + out)[-HISTORY:]
        return out

    # Closing
    def _fail(self, code, reason):
        try:
            if not self._close_sent:
                self._write(OP_CLOSE, close_payload(code, reason))
                self._close_sent = True
        except (ConnectionClosed, OSError):
            pass
        self.close_code, self.close_reason = code, reason
        self._shutdown()

    def _shutdown(self):
        self.closed = True
        try:
            self.sock.close()
        except OSError:
            pass

    def close(self, code=1000, reason='', wait=1.0):
        """The closing handshake: our close frame, then the server's answer (up to ``wait`` s)."""
        if self.closed:
            self._shutdown()             # a connection lost on its own: its socket is released too
            return
        try:
            if not self._close_sent:
                self._write(OP_CLOSE, close_payload(code, reason))
                self._close_sent = True
            deadline = time.monotonic() + wait
            while True:
                frame = self.parser.next_frame()
                if frame is None:
                    self._fill(deadline)
                    continue
                if frame[2] == OP_CLOSE:
                    self.close_code, self.close_reason = parse_close(frame[3])
                    break
        except (TimeoutError, WebSocketError, OSError):
            pass
        finally:
            self.close_code = self.close_code or code
            self._shutdown()
