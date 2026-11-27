"""Tests for websocket.py (RFC 6455 framing and handshake, RFC 7692 permessage-deflate, TLS) and the fake server.

The pure helpers are checked against the examples in the RFCs. The client is checked end to end against
tests/fake_server.py over real sockets, plain and TLS, with the test-only certificate in tests/data. Tests whose
comment starts with "was a bug" guard bugs these tests found in websocket.py.
"""
import base64
import gc
import json
import os
import socket
import ssl
import struct
import threading
import time
import traceback
import tracemalloc
import unittest
import warnings
import zlib
from collections import deque

from client.websocket import (OP_BINARY, OP_CLOSE, OP_CONT, OP_PING, OP_PONG, OP_TEXT, ConnectionClosed,
                              FrameParser, HandshakeError, ProtocolError, accept_key, apply_mask, close_payload,
                              connect, deflate_settings, encode_frame, parse_close, parse_response, split_url,
                              tls_context)

from .fake_server import FakeAPServer, WSServer, accept_response, upgrade_problems

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
CERT, KEY = os.path.join(DATA, 'test_cert.pem'), os.path.join(DATA, 'test_key.pem')   # test-only pair
SIZES = (0, 1, 125, 126, 65535, 65536, 70000)      # every length encoding and its edges
GAME = 'Rando of Time'
ALTTP = 'A Link to the Past'


def echo(conn):
    while True:
        message = conn.recv_message(timeout=5)
        if message is None:
            return
        conn.send_message(message)


def server_tls():
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(CERT, KEY)
    return context


def client_tls():
    return ssl.create_default_context(cafile=CERT)


class ServerCase(unittest.TestCase):
    def serve(self, handler, **kw):
        srv = WSServer(handler, **kw)
        url = srv.start()
        self.addCleanup(srv.stop)
        return srv, url

    def connect(self, url, **kw):
        kw.setdefault('timeout', 5)
        ws = connect(url, **kw)
        self.addCleanup(ws.close, wait=0.2)
        return ws

    def assertServerOK(self, srv):
        self.assertEqual(srv.errors, [], ''.join(''.join(traceback.format_exception(e)) for e in srv.errors))

    def finish(self, srv, count=1, timeout=5):
        """Waits until ``count`` server scripts have ended, then fails on any error in them."""
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            conns = list(srv.connections)
            if len(conns) >= count and all(c.done.is_set() for c in conns):
                break
            time.sleep(0.01)
        else:
            self.assertServerOK(srv)
            self.fail('the server script did not finish')
        self.assertServerOK(srv)


# Pure helpers
class Framing(unittest.TestCase):
    def test_rfc6455_examples(self):
        # RFC 6455 section 5.7, byte for byte
        self.assertEqual(encode_frame(OP_TEXT, b'Hello'), bytes.fromhex('810548656c6c6f'))
        self.assertEqual(encode_frame(OP_TEXT, b'Hello', mask=bytes.fromhex('37fa213d')),
                         bytes.fromhex('818537fa213d7f9f4d5158'))
        self.assertEqual(encode_frame(OP_TEXT, b'Hel', fin=False), bytes.fromhex('010348656c'))
        self.assertEqual(encode_frame(OP_CONT, b'lo'), bytes.fromhex('80026c6f'))
        self.assertEqual(encode_frame(OP_PING, b'Hello'), bytes.fromhex('890548656c6c6f'))
        self.assertEqual(encode_frame(OP_PONG, b'Hello', mask=bytes.fromhex('37fa213d')),
                         bytes.fromhex('8a8537fa213d7f9f4d5158'))
        self.assertEqual(encode_frame(OP_BINARY, bytes(256))[:4], bytes.fromhex('827e0100'))
        self.assertEqual(encode_frame(OP_BINARY, bytes(65536))[:10], bytes.fromhex('827f0000000000010000'))
        parser = FrameParser(masked=True)
        parser.feed(bytes.fromhex('818537fa213d7f9f4d5158'))
        self.assertEqual(parser.next_frame(), (True, False, OP_TEXT, b'Hello'))

    def test_header_bits(self):
        self.assertEqual(encode_frame(OP_TEXT, b'', fin=False, rsv1=True)[:2], b'\x41\x00')
        self.assertEqual(encode_frame(OP_TEXT, 'é'), b'\x81\x02' + 'é'.encode('utf-8'))   # a str goes out as UTF-8
        with self.assertRaises(ValueError):
            encode_frame(OP_TEXT, b'x', mask=b'abc')

    def test_mask_is_its_own_inverse(self):
        for size in list(range(10)) + [125, 126, 1000, 65537]:
            with self.subTest(size=size):
                data, mask = os.urandom(size), os.urandom(4)
                masked = apply_mask(data, mask)
                self.assertEqual(masked, bytes(b ^ mask[i % 4] for i, b in enumerate(data)))
                self.assertEqual(apply_mask(masked, mask), data)
        self.assertEqual(apply_mask(bytes(7), bytes(4)), bytes(7))       # zero bytes keep the length
        self.assertEqual(apply_mask(b'\x01\x00\x00', b'\x01\x00\x00\x00'), bytes(3))

    def test_round_trip_at_every_length_encoding(self):
        for size in SIZES:
            for masked in (False, True):
                for opcode in (OP_TEXT, OP_BINARY):
                    with self.subTest(size=size, masked=masked, opcode=opcode):
                        payload = os.urandom(size)
                        frame = encode_frame(opcode, payload, mask=os.urandom(4) if masked else None)
                        header = 2 + (0 if size < 126 else 2 if size < 65536 else 8) + (4 if masked else 0)
                        self.assertEqual(len(frame), header + size)
                        parser = FrameParser(masked=masked)
                        parser.feed(frame)
                        self.assertEqual(parser.next_frame(), (True, False, opcode, payload))
                        self.assertIsNone(parser.next_frame())
                        self.assertEqual(len(parser.buffer), 0)

    def test_one_byte_at_a_time(self):
        for size in (0, 1, 125, 126, 300, 65536):
            for masked in (False, True):
                with self.subTest(size=size, masked=masked):
                    payload = os.urandom(size)
                    frame = encode_frame(OP_BINARY, payload, fin=False, mask=os.urandom(4) if masked else None)
                    parser = FrameParser(masked=masked)
                    results = []
                    for i in range(len(frame)):
                        parser.feed(frame[i:i + 1])
                        results.append(parser.next_frame())
                    self.assertEqual(results.count(None), len(frame) - 1)
                    self.assertEqual(results[-1], (False, False, OP_BINARY, payload))

    def test_several_frames_in_one_feed(self):
        frames = [encode_frame(OP_TEXT, 'a', fin=False), encode_frame(OP_PING, b'p'),
                  encode_frame(OP_CONT, b'b' * 200, fin=False), encode_frame(OP_CONT, b'c' * 70000),
                  encode_frame(OP_CLOSE, close_payload(1000))]
        parser = FrameParser()
        parser.feed(b''.join(frames) + frames[0][:1])
        self.assertEqual([parser.next_frame() for _ in frames],
                         [(False, False, OP_TEXT, b'a'), (True, False, OP_PING, b'p'),
                          (False, False, OP_CONT, b'b' * 200), (True, False, OP_CONT, b'c' * 70000),
                          (True, False, OP_CLOSE, b'\x03\xe8')])
        self.assertIsNone(parser.next_frame())                  # half a frame, so it waits
        parser.feed(frames[0][1:])
        self.assertEqual(parser.next_frame(), (False, False, OP_TEXT, b'a'))

    def test_waits_for_a_whole_header(self):
        for data, masked in ((b'\x82', False), (b'\x82\x7e\x01', False), (b'\x82\x7f' + bytes(7), False),
                             (b'\x82\x85\x01\x02\x03', True), (b'\x82\x05abcd', False)):
            with self.subTest(data=data):
                parser = FrameParser(masked=masked)
                parser.feed(data)
                self.assertIsNone(parser.next_frame())

    def assertRejected(self, data, code=1002, **kw):
        parser = FrameParser(**kw)
        parser.feed(data)
        with self.assertRaises(ProtocolError) as caught:
            parser.next_frame()
        self.assertEqual(caught.exception.code, code)

    def test_rejects(self):
        mask = b'\x01\x02\x03\x04'
        cases = {
            'masked frame from a server': (encode_frame(OP_TEXT, b'x', mask=mask), {}),
            'unmasked frame from a client': (encode_frame(OP_TEXT, b'x'), {'masked': True}),
            'RSV1 without an extension': (encode_frame(OP_TEXT, b'x', rsv1=True), {}),
            'RSV2': (b'\xa1\x01x', {'allow_rsv1': True}),
            'RSV3': (b'\x91\x01x', {'allow_rsv1': True}),
            'compressed control frame': (encode_frame(OP_PING, b'', rsv1=True), {'allow_rsv1': True}),
            'fragmented ping': (encode_frame(OP_PING, b'x', fin=False), {}),
            'fragmented close': (encode_frame(OP_CLOSE, b'\x03\xe8', fin=False), {}),
            'ping of 126 bytes (header only)': (b'\x89\x7e\x00\x7e', {}),
            'close of 70000 bytes (header only)': (b'\x88\x7f' + struct.pack('>Q', 70000), {}),
            'length with the top bit set': (b'\x82\x7f' + struct.pack('>Q', 1 << 63), {}),
        }
        for opcode in (3, 4, 5, 6, 7, 0xB, 0xC, 0xD, 0xE, 0xF):
            cases[f'opcode {opcode:#x}'] = (bytes([0x80 | opcode, 0]), {})
        for name, (data, kw) in cases.items():
            with self.subTest(name):
                self.assertRejected(data, **kw)

    def test_max_size(self):
        parser = FrameParser(max_size=1000)
        parser.feed(encode_frame(OP_BINARY, bytes(1000)))
        self.assertEqual(len(parser.next_frame()[3]), 1000)
        # refused from the header alone, so we never wait for or keep any of the payload
        self.assertRejected(encode_frame(OP_BINARY, bytes(1001))[:4], 1009, max_size=1000)
        self.assertRejected(b'\x82\x7f' + struct.pack('>Q', 1 << 62), 1009)


class HandshakeHelpers(unittest.TestCase):
    def test_accept_key_rfc_example(self):
        # RFC 6455 section 1.3 (its SHA-1 bytes b37a4f2c...c4ea, base64-encoded)
        self.assertEqual(accept_key('dGhlIHNhbXBsZSBub25jZQ=='), 's3pPLMBiTxaQ9kYGzzhZRbK+xOo=')
        self.assertEqual(accept_key(b'dGhlIHNhbXBsZSBub25jZQ=='), 's3pPLMBiTxaQ9kYGzzhZRbK+xOo=')
        self.assertEqual(accept_key(' dGhlIHNhbXBsZSBub25jZQ== '), 's3pPLMBiTxaQ9kYGzzhZRbK+xOo=')

    def test_parse_close(self):
        self.assertEqual(parse_close(b''), (1005, ''))
        for code in (1000, 1001, 1002, 1003, 1007, 1008, 1009, 1010, 1011, 1012, 1013, 1014, 3000, 3999, 4000, 4999):
            self.assertEqual(parse_close(struct.pack('>H', code)), (code, ''))
        self.assertEqual(parse_close(close_payload(4000, 'bye é ✓')), (4000, 'bye é ✓'))
        with self.assertRaises(ProtocolError) as caught:
            parse_close(b'\x03')
        self.assertEqual(caught.exception.code, 1002)
        for code in (0, 999, 1004, 1005, 1006, 1015, 1016, 1100, 2000, 2999, 5000, 65535):
            with self.subTest(code=code), self.assertRaises(ProtocolError) as caught:
                parse_close(struct.pack('>H', code))
            self.assertEqual(caught.exception.code, 1002)
        for reason in (b'\xff\xfe', 'é'.encode('utf-8')[:1], b'ok\xed\xa0\x80'):      # junk, cut char, surrogate
            with self.subTest(reason=reason), self.assertRaises(ProtocolError) as caught:
                parse_close(struct.pack('>H', 1000) + reason)
            self.assertEqual(caught.exception.code, 1007)

    def test_close_payload_fits_a_control_frame(self):
        payload = close_payload(1000, 'x' * 300)
        self.assertEqual(len(payload), 125)
        parser = FrameParser()
        parser.feed(encode_frame(OP_CLOSE, payload))
        self.assertEqual(parse_close(parser.next_frame()[3]), (1000, 'x' * 123))

    def test_close_payload_does_not_cut_a_character(self):
        # was a bug: close_payload cut the UTF-8 reason mid-character at 123 bytes and the peer failed with 1007
        code, reason = parse_close(close_payload(1000, 'é' * 100))
        self.assertTrue(reason and ('é' * 100).startswith(reason))

    def test_deflate_settings(self):
        for header in (None, '', '  '):
            self.assertIsNone(deflate_settings(header))
        self.assertEqual(deflate_settings('permessage-deflate'), {'server_no_context_takeover': False})
        self.assertEqual(deflate_settings('permessage-deflate; server_no_context_takeover'),
                         {'server_no_context_takeover': True})
        self.assertEqual(deflate_settings('Permessage-Deflate; Server_No_Context_Takeover; client_max_window_bits=15'),
                         {'server_no_context_takeover': True})
        self.assertEqual(deflate_settings('permessage-deflate; server_max_window_bits="10"; '
                                          'client_no_context_takeover'), {'server_no_context_takeover': False})
        for header in ('permessage-deflate; foo', 'permessage-deflate; foo=1',
                       'permessage-deflate; server_max_window_bits=7', 'permessage-deflate; server_max_window_bits=16',
                       'permessage-deflate; client_max_window_bits=abc', 'permessage-deflate; server_max_window_bits=',
                       'permessage-deflate, permessage-deflate', 'x-webkit-deflate-frame'):
            with self.subTest(header=header), self.assertRaises(HandshakeError):
                deflate_settings(header)

    def test_deflate_settings_refuses_an_extension_not_offered_next_to_deflate(self):
        # was a bug: we accepted 'permessage-deflate, x-foo' even though we never offered x-foo (RFC 6455 4.1)
        with self.assertRaises(HandshakeError):
            deflate_settings('permessage-deflate, x-foo')

    def test_parse_response(self):
        status, headers = parse_response(b'HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n'
                                         b'CONNECTION:  Upgrade \r\nSec-WebSocket-Accept: abc=\r\nX-A: 1\r\nx-a: 2\r\n'
                                         b'X-Url: http://a:1/')
        self.assertEqual(status, 101)
        self.assertEqual(headers, {'upgrade': 'websocket', 'connection': 'Upgrade', 'sec-websocket-accept': 'abc=',
                                   'x-a': '1, 2', 'x-url': 'http://a:1/'})
        self.assertEqual(parse_response(b'HTTP/1.1 404 Not Found'), (404, {}))
        self.assertEqual(parse_response(b'HTTP/1.1 101')[0], 101)
        for raw in (b'', b'SSH-2.0-OpenSSH_9.6', b'HTTP/1.1 abc OK', b'HTTP/1.1 101 OK\r\nno colon here',
                    b'\x16\x03\x01\x02\x00'):
            with self.subTest(raw=raw), self.assertRaises(HandshakeError):
                parse_response(raw)

    def test_split_url(self):
        self.assertEqual(split_url('ws://example.com'), (False, 'example.com', 80, '/'))
        self.assertEqual(split_url('wss://example.com'), (True, 'example.com', 443, '/'))
        self.assertEqual(split_url('ws://127.0.0.1:38281'), (False, '127.0.0.1', 38281, '/'))
        self.assertEqual(split_url('wss://[::1]:5000/room?x=1#frag'), (True, '::1', 5000, '/room?x=1'))
        self.assertEqual(split_url('WS://Example.COM:1/'), (False, 'example.com', 1, '/'))
        for url in ('http://example.com', 'example.com:38281', 'ws://', 'ws://host:99999', 'ws://host:abc'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                split_url(url)

    def test_tls_context_verifies(self):
        context = tls_context()
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)


# End to end
class Handshake(ServerCase):
    def test_upgrade_request(self):
        srv, url = self.serve(lambda conn: conn.wait_closed())
        self.connect(url + '/room/abc?x=1').close()
        self.connect(url, compression=False).close()
        self.finish(srv, 2)
        first, second = srv.requests
        self.assertEqual((first['method'], first['path'], first['version']), ('GET', '/room/abc?x=1', 'HTTP/1.1'))
        self.assertEqual(upgrade_problems(first), [])
        self.assertEqual(first['headers']['host'], f'127.0.0.1:{srv.port}')
        self.assertEqual(first['headers']['sec-websocket-extensions'], 'permessage-deflate; client_max_window_bits')
        self.assertNotIn('sec-websocket-extensions', second['headers'])
        self.assertNotEqual(first['headers']['sec-websocket-key'], second['headers']['sec-websocket-key'])
        self.assertEqual(srv.connections[0].close_received, (1000, ''))

    def test_host_header_default_port_and_ipv6(self):
        srv, url = self.serve(lambda conn: conn.wait_closed())
        sock = socket.create_connection(('127.0.0.1', srv.port))
        self.connect('ws://example.com/', sock=sock).close()       # with sock= it reaches us under another name
        self.finish(srv)
        self.assertEqual(srv.requests[0]['headers']['host'], 'example.com')
        try:
            srv6, url6 = self.serve(lambda conn: conn.wait_closed(), host='::1')
        except OSError:
            self.skipTest('no IPv6 loopback')
        self.connect(url6).close()
        self.finish(srv6)
        self.assertEqual(srv6.requests[0]['headers']['host'], f'[::1]:{srv6.port}')

    def test_message_in_the_same_packet_as_the_101(self):
        second = encode_frame(OP_BINARY, b'\x00\x01\x02')

        def respond(request):
            return accept_response(request) + encode_frame(OP_TEXT, 'first') + second[:2]

        def handler(conn):
            time.sleep(0.05)
            conn.send_raw(second[2:])
            conn.wait_closed()
        srv, url = self.serve(handler, respond=respond)
        ws = self.connect(url)
        self.assertEqual(ws.recv(timeout=5), 'first')
        self.assertEqual(ws.recv(timeout=5), b'\x00\x01\x02')
        ws.close()
        self.finish(srv)

    def test_failures(self):
        accept = base64.b64encode(os.urandom(20)).decode()
        cases = {
            'HTTP 404': lambda req: b'HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n',
            'HTTP 200': lambda req: b'HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n',
            'wrong Sec-WebSocket-Accept': lambda req: accept_response(req, accept=accept),
            'no Sec-WebSocket-Accept': lambda req: accept_response(req).replace(b'Sec-WebSocket-Accept', b'X-No'),
            'no Upgrade header': lambda req: accept_response(req).replace(b'Upgrade: websocket\r\n', b''),
            'Connection without upgrade': lambda req: accept_response(req).replace(b'Connection: Upgrade',
                                                                                    b'Connection: keep-alive'),
            'extension not offered': lambda req: accept_response(req, 'x-webkit-deflate-frame'),
            'unknown deflate parameter': lambda req: accept_response(req, 'permessage-deflate; foo=1'),
            'not HTTP': lambda req: b'SSH-2.0-OpenSSH_9.6\r\n\r\n',
            'closed without an answer': lambda req: b'',
        }
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always', ResourceWarning)
            for name, respond in cases.items():
                with self.subTest(name):
                    srv, url = self.serve(lambda conn: None, respond=respond)
                    with self.assertRaises(HandshakeError):
                        connect(url, timeout=5)
            srv, url = self.serve(lambda conn: None, respond=lambda req: accept_response(req, 'permessage-deflate'))
            with self.assertRaises(HandshakeError):                     # deflate answered but never offered
                connect(url, timeout=5, compression=False)
            gc.collect()
        leaks = [w for w in caught if issubclass(w.category, ResourceWarning) and 'socket' in str(w.message)]
        self.assertEqual(leaks, [], 'a failed handshake left its socket open')

    def test_no_answer_times_out(self):
        listener = socket.create_server(('127.0.0.1', 0))              # accepts (backlog) but never answers
        self.addCleanup(listener.close)
        start = time.monotonic()
        with self.assertRaises(TimeoutError):
            connect(f'ws://127.0.0.1:{listener.getsockname()[1]}', timeout=0.5)
        self.assertLess(time.monotonic() - start, 3)


class Messages(ServerCase):
    def test_every_length_both_ways(self):
        for compression in (False, True):
            with self.subTest(compression=compression):
                srv, url = self.serve(echo, compression=compression)
                ws = self.connect(url)
                self.assertEqual(ws.deflate is not None, compression)
                for size in SIZES:
                    text = ('aé✓😀' * size)[:size]
                    ws.send(text)
                    self.assertEqual(ws.recv(timeout=5), text)
                    data = os.urandom(size)
                    ws.send(data)
                    self.assertEqual(ws.recv(timeout=5), data)
                ws.close()
                self.finish(srv)

    def test_fragments_with_a_ping_between(self):
        seen = {}

        def handler(conn):
            conn.send_frame(OP_TEXT, 'Hel', fin=False)
            conn.send_frame(OP_PING, b'are you there')
            conn.send_frame(OP_CONT, 'lo ', fin=False)
            conn.send_frame(OP_CONT, 'world')
            conn.send_message('next')
            seen['pong'] = conn.recv_frame()
            conn.wait_closed()
        srv, url = self.serve(handler, compression=False)
        ws = self.connect(url)
        self.assertEqual(ws.recv(timeout=5), 'Hello world')
        self.assertEqual(ws.recv(timeout=5), 'next')
        ws.close()
        self.finish(srv)
        self.assertEqual(seen['pong'], (True, False, OP_PONG, b'are you there'))

    def test_utf8_character_split_between_fragments(self):
        data = 'é✓😀'.encode('utf-8')

        def handler(conn):
            conn.send_frame(OP_TEXT, data[:1], fin=False)
            conn.send_frame(OP_CONT, data[1:4], fin=False)
            conn.send_frame(OP_CONT, b'', fin=False)
            conn.send_frame(OP_CONT, data[4:])
            conn.wait_closed()
        srv, url = self.serve(handler)
        ws = self.connect(url)
        self.assertEqual(ws.recv(timeout=5), 'é✓😀')
        ws.close()
        self.finish(srv)

    def test_invalid_utf8_text_fails_with_1007(self):
        seen = {}

        def handler(conn):
            conn.send_frame(OP_TEXT, b'[{"cmd": "\xff\xfe"}]')
            seen['close'] = conn.wait_closed()
        srv, url = self.serve(handler)
        ws = self.connect(url)
        with self.assertRaises(ProtocolError) as caught:
            ws.recv(timeout=5)
        self.assertEqual(caught.exception.code, 1007)
        self.assertTrue(ws.closed)
        self.finish(srv)
        self.assertEqual(seen['close'][0], 1007)

    def test_message_over_max_size(self):
        for name, frames in (('one frame', [encode_frame(OP_BINARY, bytes(1001))]),
                             ('fragments', [encode_frame(OP_BINARY, bytes(600), fin=False),
                                            encode_frame(OP_CONT, bytes(401))])):
            with self.subTest(name):
                seen = {}

                def handler(conn, frames=frames, seen=seen):
                    conn.send_frame(OP_BINARY, bytes(1000))
                    for frame in frames:
                        conn.send_raw(frame)
                    seen['close'] = conn.wait_closed()
                srv, url = self.serve(handler, compression=False)
                ws = self.connect(url, max_size=1000)
                self.assertEqual(ws.recv(timeout=5), bytes(1000))              # exactly the limit is fine
                with self.assertRaises(ProtocolError) as caught:
                    ws.recv(timeout=5)
                self.assertEqual(caught.exception.code, 1009)
                self.finish(srv)
                self.assertEqual(seen['close'][0], 1009)

    def test_recv_timeout_keeps_the_connection(self):
        go, rest = threading.Event(), threading.Event()
        frame = encode_frame(OP_TEXT, 'a frame cut in two')

        def handler(conn):
            go.wait(5)
            conn.send_raw(encode_frame(OP_TEXT, 'late') + encode_frame(OP_TEXT, 'buffered') + frame[:5])
            rest.wait(5)
            conn.send_raw(frame[5:])
            conn.wait_closed()
        srv, url = self.serve(handler, compression=False)
        ws = self.connect(url)
        start = time.monotonic()
        with self.assertRaises(TimeoutError):
            ws.recv(timeout=0.2)
        self.assertGreaterEqual(time.monotonic() - start, 0.15)
        self.assertLess(time.monotonic() - start, 2)
        self.assertFalse(ws.closed)
        go.set()
        time.sleep(0.1)                                  # let all of it arrive, so one read takes both frames
        self.assertEqual(ws.recv(timeout=5), 'late')
        self.assertEqual(ws.recv(timeout=0), 'buffered')                # already here, so no wait
        with self.assertRaises(TimeoutError):                         # half a frame stays buffered for later
            ws.recv(timeout=0.2)
        rest.set()
        self.assertEqual(ws.recv(timeout=5), 'a frame cut in two')
        ws.close()
        self.finish(srv)

    def test_ping_from_the_client(self):
        seen = {}

        def handler(conn):
            seen['ping'] = conn.recv_frame()
            conn.send_frame(OP_PONG, seen['ping'][3])
            conn.send_message('after the pong')
            conn.wait_closed()
        srv, url = self.serve(handler)
        ws = self.connect(url)
        ws.ping(b'hi')
        self.assertEqual(ws.recv(timeout=5), 'after the pong')              # the pong itself is not a message
        ws.close()
        self.finish(srv)
        self.assertEqual(seen['ping'], (True, False, OP_PING, b'hi'))

    def test_ping_payload_over_125_bytes_is_refused(self):
        # was a bug: ping() sent control frames over 125 bytes (RFC 6455 5.5), which the server refused
        srv, url = self.serve(lambda conn: conn.wait_closed())
        ws = self.connect(url)
        with self.assertRaises(ValueError):
            ws.ping(b'x' * 126)

    def test_send_from_another_thread_while_receiving(self):
        srv, url = self.serve(echo)
        ws = self.connect(url)
        texts = [f'message {i} ' + 'x' * (i * 37 % 300) for i in range(200)]

        def sender():
            for text in texts:
                ws.send(text)
        thread = threading.Thread(target=sender)
        thread.start()
        got = [ws.recv(timeout=5) for _ in texts]
        thread.join(5)
        self.assertEqual(got, texts)
        ws.close()
        self.finish(srv)

    def test_send_is_not_cut_short_by_the_recv_timeout(self):
        # was a bug: sends ran under the socket timeout recv left behind, so after recv(timeout=0.05) a send to a
        # slow reader died with ConnectionClosed(1006, 'timed out')
        sizes = []

        def handler(conn):
            time.sleep(0.6)                                   # a slow reader
            while True:
                message = conn.recv_message(timeout=10)
                if message is None:
                    return
                sizes.append(len(message))
        srv, url = self.serve(handler, compression=False, rcvbuf=8192)
        sock = socket.create_connection(('127.0.0.1', srv.port))
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 8192)
        ws = self.connect(url, sock=sock)
        with self.assertRaises(TimeoutError):
            ws.recv(timeout=0.05)
        for _ in range(8):                               # Windows takes ~2 MiB unread before a send blocks
            ws.send(bytes(1 << 20))
        ws.close()
        self.finish(srv)
        self.assertEqual(sizes, [1 << 20] * 8)


class Compression(ServerCase):
    RFC7692 = {     # the RFC 7692 section 7.2.3 examples, and every one of them is "Hello"
        'one block': ['c107f248cdc9c90700'],
        'fragmented': ['4103f248cd', '8004c9c90700'],
        'no compression': ['c10b000500faff48656c6c6f00'],
        'BFINAL block': ['c108f348cdc9c9070000'],
        'two blocks': ['c10df24805000000ffffcac9c90700'],
        'shared window': ['c107f248cdc9c90700', 'c105f200110000'],
    }

    def raw_frames(self, frames, count):
        def handler(conn):
            for frame in frames:
                conn.send_raw(bytes.fromhex(frame))
            conn.wait_closed()
        srv, url = self.serve(handler)
        ws = self.connect(url)
        got = [ws.recv(timeout=5) for _ in range(count)]
        ws.close()
        self.finish(srv)
        return got

    def test_rfc7692_examples(self):
        for name, frames in self.RFC7692.items():
            with self.subTest(name):
                count = 2 if name == 'shared window' else 1
                self.assertEqual(self.raw_frames(frames, count), ['Hello'] * count)

    def test_message_after_a_bfinal_block(self):
        # was a bug: after a BFINAL=1 block (RFC 7692 7.2.3.4) the zlib stream was over and later messages came out ''
        self.assertEqual(self.raw_frames(['c108f348cdc9c9070000', 'c107f248cdc9c90700'], 2), ['Hello', 'Hello'])

    def several_messages(self, no_context_takeover):
        messages = [json.dumps([{'cmd': 'PrintJSON', 'data': [{'text': f'Alice sent item {i} to Bob'}]}])
                    for i in range(20)]
        messages += ['', 'x', 'é' * 1000, os.urandom(70000), os.urandom(35000).hex()]
        repeated = os.urandom(1000).hex()
        seen = {'sizes': []}

        def handler(conn):
            for message in messages:
                conn.send_message(message)
            for _ in range(2):                    # the same text twice, so the second one refers back to the first
                payload = conn.compress(repeated.encode())
                seen['sizes'].append(len(payload))
                conn.send_frame(OP_TEXT, payload, rsv1=True)
            seen['compressed'] = conn.sent_compressed
            conn.wait_closed()
        srv, url = self.serve(handler, no_context_takeover=no_context_takeover)
        ws = self.connect(url)
        self.assertEqual(ws.deflate, {'server_no_context_takeover': no_context_takeover})
        self.assertEqual([ws.recv(timeout=5) for _ in messages], messages)
        self.assertEqual([ws.recv(timeout=5) for _ in range(2)], [repeated, repeated])
        ws.close()
        self.finish(srv)
        self.assertEqual(seen['compressed'], len(messages))
        return seen['sizes']

    def test_context_takeover(self):
        first, second = self.several_messages(no_context_takeover=False)
        self.assertLess(second, first // 10)         # really decoded through the previous message's window

    def test_no_context_takeover(self):
        first, second = self.several_messages(no_context_takeover=True)
        self.assertEqual(first, second)

    def test_compressed_fragments_mixed_with_plain_messages(self):
        text = '{"cmd":"RoomUpdate","checked_locations":[1,2,3]}' * 40

        def handler(conn):
            payload = conn.compress(text.encode())
            third = len(payload) // 3
            conn.send_frame(OP_TEXT, payload[:third], fin=False, rsv1=True)
            conn.send_frame(OP_PING, b'')
            conn.send_frame(OP_CONT, payload[third:2 * third], fin=False)
            conn.send_frame(OP_CONT, payload[2 * third:])
            conn.send_message('plain', compress=False)
            conn.send_message(b'\x00zipped binary')
            conn.send_message('zipped again')
            conn.wait_closed()
        srv, url = self.serve(handler)
        ws = self.connect(url)
        self.assertEqual([ws.recv(timeout=5) for _ in range(4)], [text, 'plain', b'\x00zipped binary', 'zipped again'])
        ws.close()
        self.finish(srv)

    def test_declined_compression(self):
        srv, url = self.serve(echo, compression=False)
        ws = self.connect(url)                       # offered, not accepted
        self.assertIsNone(ws.deflate)
        ws.send('plain')
        self.assertEqual(ws.recv(timeout=5), 'plain')
        ws.close()
        self.finish(srv)

    def test_compressed_frame_without_negotiation_fails(self):
        seen = {}

        def handler(conn):
            conn.send_frame(OP_TEXT, bytes.fromhex('f248cdc9c90700'), rsv1=True)
            seen['close'] = conn.wait_closed()
        srv, url = self.serve(handler, compression=False)
        ws = self.connect(url)
        with self.assertRaises(ProtocolError) as caught:
            ws.recv(timeout=5)
        self.assertEqual(caught.exception.code, 1002)
        self.finish(srv)
        self.assertEqual(seen['close'][0], 1002)

    def test_corrupt_compressed_data_fails(self):
        def handler(conn):
            conn.send_frame(OP_TEXT, b'\xff\xff\xff\xff', rsv1=True)
            conn.wait_closed()
        srv, url = self.serve(handler)
        ws = self.connect(url)
        with self.assertRaises(ProtocolError):
            ws.recv(timeout=5)
        self.finish(srv)

    def test_inflated_size_limit_is_exact(self):
        limit = 100_000
        for size, fits in ((limit, True), (limit + 1, False)):
            with self.subTest(size=size):
                srv, url = self.serve(lambda conn, size=size: (conn.send_message(b'a' * size), conn.wait_closed()))
                ws = self.connect(url, max_size=limit)
                if fits:
                    self.assertEqual(ws.recv(timeout=5), b'a' * size)
                    ws.close()
                else:
                    with self.assertRaises(ProtocolError) as caught:
                        ws.recv(timeout=5)
                    self.assertEqual(caught.exception.code, 1009)
                self.finish(srv)

    def test_zip_bomb_is_refused_without_inflating_it(self):
        limit, inflated = 1 << 20, 64 << 20
        compressor = zlib.compressobj(9, zlib.DEFLATED, -15)
        chunk = bytes(1 << 20)
        payload = b''.join(compressor.compress(chunk) for _ in range(inflated // len(chunk)))
        payload = (payload + compressor.flush(zlib.Z_SYNC_FLUSH))[:-4]
        del chunk
        self.assertLess(len(payload), limit)          # the frame itself is small
        seen = {}

        def handler(conn):
            conn.send_frame(OP_BINARY, payload, rsv1=True)
            seen['close'] = conn.wait_closed()
        srv, url = self.serve(handler)
        ws = self.connect(url, max_size=limit)
        tracemalloc.start()
        try:
            with self.assertRaises(ProtocolError) as caught:
                ws.recv(timeout=10)
            peak = tracemalloc.get_traced_memory()[1]
        finally:
            tracemalloc.stop()
        self.assertEqual(caught.exception.code, 1009)
        self.assertLess(peak, 16 << 20, f'{peak >> 20} MiB allocated for a {limit >> 20} MiB limit')
        self.finish(srv)
        self.assertEqual(seen['close'][0], 1009)


class Closing(ServerCase):
    def test_server_closes(self):
        def handler(conn):
            conn.send_message('bye soon')
            conn.close(4000, 'gone fishing')
        srv, url = self.serve(handler)
        ws = self.connect(url)
        self.assertEqual(ws.recv(timeout=5), 'bye soon')
        with self.assertRaises(ConnectionClosed) as caught:
            ws.recv(timeout=5)
        self.assertEqual((caught.exception.code, caught.exception.reason), (4000, 'gone fishing'))
        self.assertTrue(ws.closed)
        self.assertEqual((ws.close_code, ws.close_reason), (4000, 'gone fishing'))
        with self.assertRaises(ConnectionClosed):
            ws.recv(timeout=1)
        with self.assertRaises(ConnectionClosed):
            ws.send('too late')
        self.finish(srv)
        self.assertEqual(srv.connections[0].close_received, (4000, ''))      # the client answered

    def test_server_closes_without_a_code(self):
        def handler(conn):
            conn.send_frame(OP_CLOSE, b'')
            conn.close_sent = True
            conn.wait_closed()
        srv, url = self.serve(handler)
        ws = self.connect(url)
        with self.assertRaises(ConnectionClosed) as caught:
            ws.recv(timeout=5)
        self.assertEqual(caught.exception.code, 1005)
        self.finish(srv)
        self.assertIsNotNone(srv.connections[0].close_received)

    def test_server_close_with_a_reserved_code_fails(self):
        def handler(conn):
            conn.send_frame(OP_CLOSE, struct.pack('>H', 1006))
            conn.close_sent = True
            conn.wait_closed()
        srv, url = self.serve(handler)
        ws = self.connect(url)
        with self.assertRaises(ProtocolError) as caught:
            ws.recv(timeout=5)
        self.assertEqual(caught.exception.code, 1002)
        self.finish(srv)

    def test_client_closes(self):
        seen = {}

        def handler(conn):
            seen['message'] = conn.recv_message()
            seen['close'] = conn.close_received
        srv, url = self.serve(handler)
        ws = self.connect(url)
        start = time.monotonic()
        ws.close(1000, 'done')
        self.assertLess(time.monotonic() - start, 1)
        self.assertTrue(ws.closed)
        self.assertEqual(ws.close_code, 1000)
        ws.close()                                       # a second close does nothing
        self.finish(srv)
        self.assertEqual(seen, {'message': None, 'close': (1000, 'done')})

    def test_close_without_an_answer_gives_up(self):
        release = threading.Event()
        srv, url = self.serve(lambda conn: release.wait(5))
        self.addCleanup(release.set)                     # cleanups run last-first, so this one runs before srv.stop
        ws = self.connect(url)
        start = time.monotonic()
        ws.close(wait=0.3)
        self.assertGreaterEqual(time.monotonic() - start, 0.25)
        self.assertLess(time.monotonic() - start, 2)
        self.assertTrue(ws.closed)
        release.set()

    def abrupt(self, how):
        go = threading.Event()

        def handler(conn):
            conn.send_message('hi')
            go.wait(5)
            time.sleep(0.05)
            conn.shutdown() if how == 'fin' else conn.abort()
        srv, url = self.serve(handler)
        self.addCleanup(go.set)
        ws = self.connect(url)
        self.assertEqual(ws.recv(timeout=5), 'hi')
        go.set()
        outcome = []

        def reader():                                    # recv without a timeout must wake up
            try:
                ws.recv()
            except Exception as error:  # noqa: BLE001
                outcome.append(error)
        thread = threading.Thread(target=reader, daemon=True)
        thread.start()
        thread.join(5)
        self.assertFalse(thread.is_alive(), 'recv() hung after the connection was lost')
        self.assertIsInstance(outcome[0], ConnectionClosed)
        self.assertEqual(outcome[0].code, 1006)
        self.assertTrue(ws.closed)
        with self.assertRaises(ConnectionClosed):
            ws.send('x')
        return ws

    def test_abrupt_disconnect_fin(self):
        self.abrupt('fin')

    def test_abrupt_disconnect_rst(self):
        self.abrupt('rst')

    def test_socket_released_after_a_lost_connection(self):
        ws = self.abrupt('fin')                          # no socket left open until garbage collection
        self.assertEqual(ws.sock.fileno(), -1)
        ws.close()
        self.assertEqual(ws.sock.fileno(), -1)


@unittest.skipUnless(os.path.isfile(CERT) and os.path.isfile(KEY), 'tests/data/test_cert.pem missing')
class TLS(ServerCase):
    def test_wss_with_a_trusted_certificate(self):
        srv, url = self.serve(echo, ssl_context=server_tls())
        self.assertTrue(url.startswith('wss://127.0.0.1:'))
        ws = self.connect(url, ssl_context=client_tls())
        self.assertTrue(ws.secure)
        self.assertIsInstance(ws.sock, ssl.SSLSocket)
        for size in (0, 125, 126, 70000, 300000):
            data = os.urandom(size)
            ws.send(data)
            self.assertEqual(ws.recv(timeout=5), data)
        with self.assertRaises(TimeoutError):
            ws.recv(timeout=0.2)
        ws.send('still here')
        self.assertEqual(ws.recv(timeout=5), 'still here')
        ws.close()
        self.finish(srv)
        self.assertEqual(srv.connections[0].close_received, (1000, ''))

    def test_localhost_name(self):
        srv, url = self.serve(echo, ssl_context=server_tls())
        sock = socket.create_connection(('127.0.0.1', srv.port))
        ws = self.connect(f'wss://localhost:{srv.port}', ssl_context=client_tls(), sock=sock)
        ws.send('hi')
        self.assertEqual(ws.recv(timeout=5), 'hi')
        ws.close()
        self.finish(srv)

    def test_default_context_refuses_a_self_signed_certificate(self):
        srv, url = self.serve(echo, ssl_context=server_tls())
        with self.assertRaises(ssl.SSLCertVerificationError):
            connect(url, timeout=5)
        with self.assertRaises(ssl.SSLCertVerificationError):
            connect(url, timeout=5, ssl_context=tls_context())

    def test_hostname_mismatch(self):
        srv, url = self.serve(echo, ssl_context=server_tls())
        sock = socket.create_connection(('127.0.0.1', srv.port))
        with self.assertRaises(ssl.SSLCertVerificationError):
            connect(f'wss://example.invalid:{srv.port}', timeout=5, ssl_context=client_tls(), sock=sock)

    def test_wss_to_a_plain_server(self):
        # protocol.tls_unsupported() relies on this being an SSLError and never a certificate error
        srv, url = self.serve(echo)
        with self.assertRaises(ssl.SSLError) as caught:
            connect(url.replace('ws://', 'wss://'), timeout=5, ssl_context=client_tls())
        self.assertNotIsInstance(caught.exception, ssl.SSLCertVerificationError)

    def test_server_close_and_abrupt_disconnect(self):
        def handler(conn):
            conn.send_message('one')
            conn.close(4001, 'tls bye')
        srv, url = self.serve(handler, ssl_context=server_tls())
        ws = self.connect(url, ssl_context=client_tls())
        self.assertEqual(ws.recv(timeout=5), 'one')
        with self.assertRaises(ConnectionClosed) as caught:
            ws.recv(timeout=5)
        self.assertEqual(caught.exception.code, 4001)
        self.finish(srv)
        srv2, url2 = self.serve(lambda conn: (conn.send_message('two'), conn.shutdown()), ssl_context=server_tls())
        ws2 = self.connect(url2, ssl_context=client_tls())
        self.assertEqual(ws2.recv(timeout=5), 'two')
        with self.assertRaises(ConnectionClosed) as caught:
            ws2.recv(timeout=5)
        self.assertEqual(caught.exception.code, 1006)


# The fake server
class Peer:
    """A raw Archipelago client on our WebSocket that sends and reads JSON packets."""

    def __init__(self, ws):
        self.ws, self.pending = ws, deque()

    def send(self, *packets):
        self.ws.send(json.dumps(list(packets)))

    def next(self, timeout=5):
        while not self.pending:
            self.pending.extend(json.loads(self.ws.recv(timeout=timeout)))
        return self.pending.popleft()

    def until(self, cmd, timeout=5):
        """Returns (the first ``cmd`` packet, the packets before it)."""
        before = []
        while True:
            packet = self.next(timeout)
            if packet['cmd'] == cmd:
                return packet, before
            before.append(packet)

    def nothing(self, wait=0.2):
        try:
            return json.loads(self.ws.recv(timeout=wait))
        except TimeoutError:
            return None


def login(**fields):
    packet = {'cmd': 'Connect', 'password': None, 'game': GAME, 'name': 'Alice', 'uuid': 'test',
              'version': {'major': 0, 'minor': 6, 'build': 6, 'class': 'Version'}, 'items_handling': 0b111,
              'tags': [], 'slot_data': True}
    packet.update(fields)
    return packet


BOB_ITEM = {'item': 1001, 'location': 2000, 'player': 2, 'flags': 1}
OWN_ITEM = {'item': 1002, 'location': 1003, 'player': 1, 'flags': 0}
START_ITEM = {'item': 1003, 'location': -2, 'player': 0, 'flags': 0}


class FakeServerBehaviour(unittest.TestCase):
    def open(self, srv=None, **kw):
        srv = srv or FakeAPServer(slot_data={'seed': '12345', 'mailbox_version': 1})
        url = srv.start()
        self.addCleanup(srv.stop)
        ws = connect(url, timeout=5, **kw)
        self.addCleanup(ws.close, wait=0.2)
        peer = Peer(ws)
        return srv, peer, peer.next()

    def test_room_info_and_datapackage(self):
        srv, peer, room = self.open()
        self.assertEqual(room['cmd'], 'RoomInfo')
        self.assertEqual(room['games'], [ALTTP, GAME])
        self.assertEqual(set(room['datapackage_checksums']), {ALTTP, GAME})
        self.assertEqual((room['password'], room['seed_name'], room['version']['class']), (False, 'fake-seed', 'Version'))
        peer.send({'cmd': 'GetDataPackage', 'games': [ALTTP]})
        package, _ = peer.until('DataPackage')
        games = package['data']['games']
        self.assertEqual(list(games), [ALTTP])
        self.assertEqual(games[ALTTP]['checksum'], room['datapackage_checksums'][ALTTP])
        self.assertEqual(games[ALTTP]['item_name_to_id'][f'{ALTTP} item 1001'], 1001)
        self.assertEqual(srv.get_datapackage_requests, [[ALTTP]])

    def test_refusals_then_login(self):
        srv, peer, room = self.open(FakeAPServer(password='pw'))
        self.assertTrue(room['password'])
        for fields, error in (({'password': 'nope'}, 'InvalidPassword'), ({'password': 'pw', 'name': 'Carol'},
                                                                          'InvalidSlot'),
                              ({'password': 'pw', 'game': ALTTP}, 'InvalidGame'),
                              ({'password': 'pw', 'items_handling': 'all'}, 'InvalidItemsHandling'),
                              ({'password': 'pw', 'version': None}, 'IncompatibleVersion')):
            with self.subTest(error):
                peer.send(login(**fields))
                refused, _ = peer.until('ConnectionRefused')
                self.assertEqual(refused['errors'], [error])
        self.assertEqual(srv.connects, 0)
        peer.send({'cmd': 'LocationChecks', 'locations': [1000]})      # ignored before Connected
        peer.send(login(password='pw'))
        connected, _ = peer.until('Connected')
        self.assertEqual(srv.connects, 1)
        self.assertEqual(srv.checked_locations, set())
        self.assertEqual([p['cmd'] for p in srv.ignored_packets], ['LocationChecks'])

    def test_connected(self):
        srv, peer, _ = self.open(FakeAPServer(slot_data={'seed': '12345'}, checked=[1000, 1001], items=[BOB_ITEM]))
        peer.send(login())
        connected = peer.next()
        self.assertEqual(connected['cmd'], 'Connected')
        self.assertEqual((connected['team'], connected['slot'], connected['slot_data']), (0, 1, {'seed': '12345'}))
        self.assertEqual([(p['slot'], p['name']) for p in connected['players']], [(1, 'Alice'), (2, 'Bob')])
        self.assertEqual(connected['slot_info']['2'], {'name': 'Bob', 'game': ALTTP, 'type': 1, 'group_members': [],
                                                       'class': 'NetworkSlot'})
        self.assertEqual(connected['checked_locations'], [1000, 1001])
        self.assertEqual(len(connected['missing_locations']), 198)
        received = peer.next()
        self.assertEqual((received['cmd'], received['index']), ('ReceivedItems', 0))
        self.assertEqual(received['items'], [dict(BOB_ITEM, **{'class': 'NetworkItem'})])
        join, _ = peer.until('PrintJSON')
        self.assertEqual(join['type'], 'Join')
        peer.send(login(slot_data=False))
        self.assertNotIn('slot_data', peer.until('Connected')[0])

    def test_items_handling_filters_and_indexes(self):
        for handling, expected in ((0b000, None), (0b001, [BOB_ITEM]), (0b101, [BOB_ITEM, START_ITEM]),
                                   (0b111, [BOB_ITEM, OWN_ITEM, START_ITEM])):
            with self.subTest(handling=bin(handling)):
                srv, peer, _ = self.open(FakeAPServer(items=[BOB_ITEM, OWN_ITEM, START_ITEM]))
                peer.send(login(items_handling=handling))
                peer.until('Connected')
                if expected is None:
                    self.assertNotIn('ReceivedItems', [p['cmd'] for p in list(peer.pending)])
                    continue
                received, _ = peer.until('ReceivedItems')
                self.assertEqual([i['item'] for i in received['items']], [i['item'] for i in expected])
                item = srv.send_item(1500, from_player=2, location=2001)
                pushed, _ = peer.until('ReceivedItems')
                self.assertEqual((pushed['index'], pushed['items']), (len(expected), [item]))
                srv.send_item(1501, from_player=1, location=1009)          # our own world, only with bit 1
                peer.send({'cmd': 'Sync'})
                synced, _ = peer.until('ReceivedItems')
                if handling & 0b010:
                    self.assertEqual(synced, {'cmd': 'ReceivedItems', 'index': len(expected) + 1,
                                              'items': [dict(srv.items[-1])]})
                    synced, _ = peer.until('ReceivedItems')
                self.assertEqual(synced['index'], 0)
                self.assertEqual(len(synced['items']), len(expected) + 1 + bool(handling & 0b010))

    def test_location_checks(self):
        srv, peer, _ = self.open(FakeAPServer(location_items={1005: (1, 4242, 1)}, items=[BOB_ITEM]))
        peer.send(login())
        peer.until('ReceivedItems')
        peer.send({'cmd': 'LocationChecks', 'locations': [1005, 1000]})
        update, before = peer.until('RoomUpdate')
        before = [p for p in before if p.get('type') != 'Join']
        self.assertEqual([p['cmd'] for p in before], ['PrintJSON', 'PrintJSON', 'ReceivedItems'])   # server order
        own, bob, received = before
        self.assertEqual((own['type'], own['receiving'], own['data'][1]['text']), ('ItemSend', 1, ' found their '))
        self.assertEqual((bob['receiving'], bob['item']), (2, {'item': 1001, 'location': 1000, 'player': 1,
                                                               'flags': 0, 'class': 'NetworkItem'}))
        self.assertEqual([part.get('type', 'text') for part in bob['data']],
                         ['player_id', 'text', 'item_id', 'text', 'player_id', 'text', 'location_id', 'text'])
        self.assertEqual((received['index'], [i['item'] for i in received['items']]), (1, [4242]))
        self.assertEqual(update['checked_locations'], [1000, 1005])
        self.assertEqual(srv.checked_locations, {1000, 1005})
        peer.send({'cmd': 'LocationChecks', 'locations': [1000]})          # already known, nothing new
        self.assertIsNone(peer.nothing())

    def test_chat_status_and_junk(self):
        srv, peer, _ = self.open()
        peer.send(login())
        peer.until('Connected')
        peer.send({'cmd': 'Say', 'text': 'hello world'}, {'cmd': 'StatusUpdate', 'status': 20},
                  {'cmd': 'StatusUpdate', 'status': 30}, {'cmd': 'Frobnicate'})
        chat = peer.until('PrintJSON')[0]
        while chat['type'] != 'Chat':
            chat = peer.until('PrintJSON')[0]
        self.assertEqual((chat['message'], chat['data'][0]['text']), ('hello world', 'Alice: hello world'))
        self.assertEqual(peer.until('PrintJSON')[0]['type'], 'Goal')
        invalid, _ = peer.until('InvalidPacket')
        self.assertEqual(invalid['original_cmd'], 'Frobnicate')
        peer.ws.send('not json')
        self.assertEqual(peer.until('InvalidPacket')[0]['type'], 'cmd')
        self.assertEqual(srv.said, ['hello world'])
        self.assertEqual(srv.status_updates, [20, 30])
        self.assertEqual([p['cmd'] for p in srv.received_packets()],
                         ['Connect', 'Say', 'StatusUpdate', 'StatusUpdate', 'Frobnicate'])
        self.assertEqual(srv.errors, [])

    def test_drop_clients_and_stop(self):
        srv, peer, _ = self.open()
        peer.send(login())
        peer.until('Connected')
        srv.drop_clients()
        with self.assertRaises(ConnectionClosed) as caught:
            while True:
                peer.ws.recv(timeout=5)
        self.assertEqual(caught.exception.code, 1006)
        again = Peer(connect(srv.url, timeout=5))
        self.addCleanup(again.ws.close, wait=0.2)
        again.next()
        again.send(login())
        again.until('Connected')
        self.assertEqual(srv.connects, 2)
        srv.stop()
        with self.assertRaises(ConnectionClosed) as caught:
            while True:
                again.ws.recv(timeout=5)
        self.assertEqual(caught.exception.code, 1001)
        self.assertEqual(srv.errors, [])

    @unittest.skipUnless(os.path.isfile(CERT), 'tests/data/test_cert.pem missing')
    def test_tls_without_context_takeover(self):
        srv, peer, room = self.open(FakeAPServer(ssl_context=server_tls(), no_context_takeover=True),
                                    ssl_context=client_tls())
        self.assertTrue(srv.url.startswith('wss://'))
        self.assertEqual(peer.ws.deflate, {'server_no_context_takeover': True})
        peer.send({'cmd': 'GetDataPackage'}, login())
        package, _ = peer.until('DataPackage')
        self.assertEqual(set(package['data']['games']), {ALTTP, GAME})
        peer.until('Connected')


if __name__ == '__main__':
    unittest.main()
