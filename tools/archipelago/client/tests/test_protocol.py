"""Pure parts of the Archipelago protocol client (no network)."""
import os
import ssl
import tempfile
import unittest

from client import protocol as P
from client import websocket


class Addresses(unittest.TestCase):
    def test_server_urls(self):
        self.assertEqual(P.server_urls('archipelago.gg:38281'), ['wss://archipelago.gg:38281', 'ws://archipelago.gg:38281'])
        self.assertEqual(P.server_urls(' archipelago.gg '), ['wss://archipelago.gg:38281', 'ws://archipelago.gg:38281'])
        self.assertEqual(P.server_urls('/connect localhost:1234'), ['wss://localhost:1234', 'ws://localhost:1234'])
        self.assertEqual(P.server_urls('ws://host:1'), ['ws://host:1'])
        self.assertEqual(P.server_urls('[::1]:5000'), ['wss://[::1]:5000', 'ws://[::1]:5000'])
        self.assertEqual(P.server_urls('[::1]'), ['wss://[::1]:38281', 'ws://[::1]:38281'])
        for bad in ('', '   ', 'http://x'):
            with self.assertRaises(P.ClientError):
                P.server_urls(bad)

    def test_loopback(self):
        self.assertTrue(P.is_loopback('ws://localhost:1'))
        self.assertTrue(P.is_loopback('ws://127.0.0.1:1'))
        self.assertTrue(P.is_loopback('ws://[::1]:1'))
        self.assertFalse(P.is_loopback('ws://archipelago.gg:1'))
        self.assertFalse(P.is_loopback('ws://10.0.0.1:1'))

    def test_tls_fallback_rule(self):
        self.assertFalse(P.tls_unsupported(ssl.SSLCertVerificationError('bad cert')))
        self.assertTrue(P.tls_unsupported(ssl.SSLError('wrong version number')))
        self.assertTrue(P.tls_unsupported(ConnectionResetError()))
        self.assertTrue(P.tls_unsupported(websocket.HandshakeError('did not receive a valid HTTP response')))
        self.assertFalse(P.tls_unsupported(TimeoutError('timed out')))


class Reporter(unittest.TestCase):
    def test_pending_only_new_and_own(self):
        r = P.LocationReporter([1, 2, 3, 4])
        r.reset_connection([1])
        self.assertEqual(r.pending({1, 2, 3, 99}), [2, 3])     # 99 is not this slot's: never sent
        r.sent.update([2, 3])
        self.assertEqual(r.pending({1, 2, 3}), [])
        self.assertEqual(r.counts({2, 3}), (3, 4))
        r.reset_connection([])                                  # a new connection: the server is asked again
        self.assertEqual(r.pending({2, 3}), [2, 3])


class Rendering(unittest.TestCase):
    def test_render_parts(self):
        def names(kind, value, player):
            return {'player': {1: 'Alice', 2: 'Bob'}, 'item': {7: 'Hammer'}, 'location': {9: 'Chest'}}[kind][value]
        text, tags = P.render([{'type': 'player_id', 'text': '1'}, {'text': ' sent '},
                               {'type': 'item_id', 'text': '7', 'player': 2, 'flags': 1}, {'text': ' to '},
                               {'type': 'player_id', 'text': '2'}, {'text': ' ('},
                               {'type': 'location_id', 'text': '9', 'player': 1}, {'text': ')'}], names)
        self.assertEqual(text, 'Alice sent Hammer to Bob (Chest)')
        self.assertIn((11, 17, 'progression'), tags)
        self.assertEqual(text[0:5], 'Alice')
        self.assertEqual(P.render([{'type': 'item_id', 'text': 'x'}], names)[0], 'x')   # junk id: shown as is
        self.assertEqual(P.render(None, names), ('', []))


class Cache(unittest.TestCase):
    def test_datapackage_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            cache = P.DataPackageCache(os.path.join(folder, 'dp'))
            self.assertIsNone(cache.load('Game: A/B', 'abc'))
            cache.save('Game: A/B', {'checksum': 'abc', 'item_name_to_id': {'X': 1}})
            self.assertEqual(cache.load('Game: A/B', 'abc')['item_name_to_id'], {'X': 1})
            self.assertIsNone(cache.load('Game: A/B', 'other'))
            self.assertIsNone(cache.load('Game: A/B', None))
            self.assertIsNone(P.DataPackageCache(None).load('g', 'abc'))


class Names(unittest.TestCase):
    def test_names_before_and_after_datapackage(self):
        client = P.APClient('Rando of Time', 'Alice', 'localhost', location_names={101: 'KF Chest'})
        self.assertEqual(client.name('location', 101, None), 'KF Chest')
        self.assertEqual(client.name('item', 5, None), 'item 5')
        self.assertEqual(client.name('player', 0, None), 'Archipelago')
        client._learn('Rando of Time', {'item_name_to_id': {'Bow': 5}, 'location_name_to_id': {}})
        self.assertEqual(client.item_name(5), 'Bow')
        self.assertEqual(client.describe_received({'item': 5, 'player': 0, 'location': -2})[2], 'starting inventory')
        with self.assertRaises(P.ClientError):
            P.APClient('g', '', 'localhost')


class PlainFallback(unittest.TestCase):
    """Ported from OotrR's tests/test_ap_client.py (MIT, Copyright (c) 2026 Mozencaz): when wss may fall back to ws."""

    def failing(self, error, attempts):
        def connect(url, **options):
            attempts.append(url)
            if url.startswith('wss://'):
                raise error
            return object()
        return connect

    def test_rules(self):
        attempts = []
        client = P.APClient('g', 'Alice', 'host:1', connect=self.failing(ssl.SSLCertVerificationError('bad'), attempts))
        with self.assertRaisesRegex(P.ClientError, 'certificate'):
            client._open()
        self.assertEqual(attempts, ['wss://host:1'])         # a bad certificate is never retried unencrypted
        attempts.clear()
        client = P.APClient('g', 'Alice', 'host:1', connect=self.failing(ssl.SSLError('wrong version'), attempts))
        client._open()
        self.assertEqual(attempts, ['wss://host:1', 'ws://host:1'])
        self.assertIs(client.encrypted, False)
        attempts.clear()
        client = P.APClient('g', 'Alice', 'host:1', 'secret', connect=self.failing(ssl.SSLError('x'), attempts))
        with self.assertRaisesRegex(P.ClientError, 'ws://host:1'):
            client._open()                                    # never the password in clear unless ws:// typed
        self.assertEqual(attempts, ['wss://host:1'])
        attempts.clear()
        client = P.APClient('g', 'Alice', 'localhost:1', 'secret', connect=self.failing(ssl.SSLError('x'), attempts))
        client._open()                                        # this machine: nobody in between
        self.assertEqual(attempts, ['wss://localhost:1', 'ws://localhost:1'])
        client = P.APClient('g', 'Alice', 'ws://host:1', 'secret', connect=self.failing(AssertionError(), attempts))
        client._open()
        self.assertIs(client.encrypted, False)
        client = P.APClient('g', 'Alice', 'host:1', connect=self.failing(TimeoutError('timed out'), attempts))
        with self.assertRaises(TimeoutError):
            client._open()                                    # refused or slow is no reason to go unencrypted


class Packets(unittest.TestCase):
    class Sock:
        def __init__(self):
            self.sent = []

        def send(self, text):
            import json
            self.sent.extend(json.loads(text))

    def connected(self, client, sock, **slot_data):
        client._handle(sock, {'cmd': 'Connected', 'team': 0, 'slot': 1, 'checked_locations': [5],
                              'players': [{'team': 0, 'slot': 1, 'alias': 'Alice', 'name': 'Alice'},
                                          {'team': 0, 'slot': 2, 'alias': 'Bobby', 'name': 'Bob'}],
                              'slot_info': {'1': {'name': 'Alice', 'game': 'g'}, '2': {'name': 'Bob', 'game': 'h'}},
                              'slot_data': dict({'seed': '1', 'mailbox_version': 1}, **slot_data)})

    def test_received_items_index_and_resync(self):
        client, sock = P.APClient('g', 'Alice', 'host:1', seed='1'), self.Sock()
        self.connected(client, sock)
        self.assertEqual(sock.sent[-1], {'cmd': 'StatusUpdate', 'status': P.CLIENT_PLAYING})
        item = {'item': 7, 'location': 50, 'player': 2, 'flags': 1}
        client._handle(sock, {'cmd': 'ReceivedItems', 'index': 0, 'items': [item, item]})
        client._handle(sock, {'cmd': 'ReceivedItems', 'index': 2, 'items': [item]})
        self.assertEqual(len(client.received), 3)
        client._handle(sock, {'cmd': 'ReceivedItems', 'index': 5, 'items': [item]})   # a gap: ask again
        self.assertEqual(sock.sent[-1], {'cmd': 'Sync'})
        self.assertEqual(len(client.received), 3)
        client._handle(sock, {'cmd': 'ReceivedItems', 'index': 0, 'items': [item]})   # the full list replaces
        self.assertEqual(len(client.received), 1)
        self.assertEqual(client.name('player', 2, None), 'Bobby')

    def test_refusals_and_other_seed(self):
        client, sock = P.APClient('g', 'Alice', 'host:1', seed='1'), self.Sock()
        with self.assertRaisesRegex(P.ClientError, 'InvalidPassword'):
            client._handle(sock, {'cmd': 'ConnectionRefused', 'errors': ['InvalidPassword']})
        with self.assertRaises(ConnectionError):
            client._handle(sock, {'cmd': 'ConnectionRefused', 'errors': ['SomethingNew']})
        with self.assertRaisesRegex(P.ClientError, 'another seed'):
            self.connected(client, sock, seed='2')
        with self.assertRaisesRegex(P.ClientError, 'item-delivery version 9'):
            self.connected(client, sock, mailbox_version=9)

    def test_checks_and_goal_flush(self):
        client, sock = P.APClient('g', 'Alice', 'host:1', locations=[5, 6, 7]), self.Sock()
        client.update({5, 6, 99}, goal=False)
        client._flush(sock)
        self.assertEqual(sock.sent, [])                       # nothing before Connected
        self.connected(client, sock)
        client._flush(sock)
        self.assertIn({'cmd': 'LocationChecks', 'locations': [6]}, sock.sent)   # 5 known, 99 not ours
        sock.sent.clear()
        client._flush(sock)
        self.assertEqual(sock.sent, [])                       # each once
        client.update({5, 6}, goal=True)
        client._flush(sock)
        self.assertEqual(sock.sent, [{'cmd': 'StatusUpdate', 'status': P.CLIENT_GOAL}])
        client.update(set(), goal=False)                      # the goal latches
        client._flush(sock)
        self.assertEqual(len(sock.sent), 1)


if __name__ == '__main__':
    unittest.main()
