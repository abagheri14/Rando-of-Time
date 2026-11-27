"""End to end: a Session (the client as the window runs it) against the fake Archipelago server, a save folder and a
simulated game behind the mailbox. Connect, checks out, the goal, items in, a game that isn't running yet,
reconnects (nothing delivered twice), refusals, chat."""
import json
import os
import tempfile
import time
import unittest
from unittest import mock

from client import protocol, session as session_module
from client.session import Session

from .fake_server import FakeAPServer
from .helpers import FakeGame, make_save, write_seed

GAME = 'Rando of Time'
LOCATIONS = {'KF Chest': 101, 'KF Gift': 102, 'KF Pot': 103}
CHECKS = [{'name': 'KF Chest', 'kind': 'chest', 'flags': [{'t': 'b64', 'h': '777'}]},
          {'name': 'KF Gift', 'kind': 'npc', 'flags': [{'t': 'bool', 'n': 'Gift_Got'}]},
          {'name': 'KF Pot', 'kind': 'pot', 'flags': [{'t': 'bit', 'a': 'RandoChecked', 'i': 3}]}]
MARKER = 'RandoAP_Seed_K3yK3yK3y'
ITEMS = {'Bow': 77, 'Hookshot': 78, 'Boomerang': 79}
CODES = {'Bow': 5, 'Hookshot': 9, 'Boomerang': 3}
DATAPACKAGE = {GAME: {'item_name_to_id': ITEMS, 'location_name_to_id': LOCATIONS, 'checksum': 'ours1'},
               'A Link to the Past': {'item_name_to_id': {'Hammer': 1000}, 'location_name_to_id': {'Bob Chest': 2000},
                                      'checksum': 'alttp1'}}


def wait(predicate, timeout=8.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


class SessionTest(unittest.TestCase):
    def setUp(self):
        self.patches = [mock.patch.object(session_module, 'CHECK_SECONDS', 0.1),
                        mock.patch.object(session_module, 'FAST_SECONDS', 0.02),
                        mock.patch.object(session_module, 'IDLE_SECONDS', 0.05),
                        mock.patch.object(protocol, 'RETRY_SECONDS', (0.2,))]
        for p in self.patches:
            p.start()
        self.tmp = tempfile.TemporaryDirectory()
        root = self.tmp.name
        self.seed_dir = os.path.join(root, 'OUT')
        write_seed(self.seed_dir, LOCATIONS, CHECKS)
        self.tables = os.path.join(root, 'data', 'archipelago')
        os.makedirs(self.tables)
        with open(os.path.join(self.tables, 'mailbox.json'), 'w', encoding='utf-8') as stream:
            json.dump({'mailbox_version': 1, 'codes': CODES}, stream)
        with open(os.path.join(self.tables, 'ids.json'), 'w', encoding='utf-8') as stream:
            json.dump({'format': 1, 'game': GAME, 'items': ITEMS, 'locations': LOCATIONS}, stream)
        self.save_dir = os.path.join(root, 'save', 'acct', 'slot_00')
        os.makedirs(self.save_dir)
        self.servers, self.sessions = [], []

    def tearDown(self):
        for s in self.sessions:
            s.stop()
        for srv in self.servers:
            srv.stop()
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def write_save(self, **kw):
        bools = dict({MARKER: True}, **kw.pop('bools', {}))
        path = os.path.join(self.save_dir, 'progress.sav')
        with open(path, 'wb') as stream:
            stream.write(make_save(bools=bools, **kw))
        self.writes = getattr(self, 'writes', 0) + 1           # a new mtime every write
        later = time.time() + self.writes
        os.utime(path, (later, later))

    def server(self, **kw):
        args = dict(game=GAME, slot_name='Alice', slot=1, slot_data={'seed': '12345', 'mailbox_version': 1},
                    other_players={2: ('Bob', 'A Link to the Past')}, datapackage=DATAPACKAGE)
        args.update(kw)
        srv = FakeAPServer(**args)
        self.servers.append(srv)
        return srv, srv.start()

    def session(self, url, game=None, password='', **kw):
        s = Session(self.seed_dir, url, '', password, save_root=os.path.join(self.tmp.name, 'save'),
                    game=game, cache_dir=os.path.join(self.tmp.name, 'cache'),
                    marks_path=os.path.join(self.tmp.name, 'no-tracker.json'), tables=self.tables, **kw)
        self.sessions.append(s)
        s.start()
        return s

    # Checks out
    def test_connect_checks_and_goal(self):
        self.write_save(bools={'Gift_Got': True}, bool64=[777])
        srv, url = self.server()
        s = self.session(url)
        self.assertTrue(wait(lambda: s.summary()['connected']), s.summary()['status'])
        self.assertTrue(wait(lambda: srv.checked_locations >= {101, 102}))
        self.assertNotIn(103, srv.checked_locations)
        self.assertIn(protocol.CLIENT_PLAYING, srv.status_updates)
        self.write_save(bools={'Gift_Got': True}, bool64=[777], arrays={'RandoChecked': [False] * 3 + [True]})
        self.assertTrue(wait(lambda: 103 in srv.checked_locations))
        self.assertNotIn(protocol.CLIENT_GOAL, srv.status_updates)
        self.write_save(bools={'Gift_Got': True}, enums={'Step_Defeat_Ganon': 'Complete'})
        self.assertTrue(wait(lambda: protocol.CLIENT_GOAL in srv.status_updates))
        sent = [p for p in srv.received_packets() if p.get('cmd') == 'LocationChecks']
        flat = [i for p in sent for i in p['locations']]
        self.assertEqual(sorted(flat), sorted(set(flat)))          # each location sent once
        connect = next(p for p in srv.received_packets() if p.get('cmd') == 'Connect')
        self.assertEqual((connect['game'], connect['name'], connect['items_handling']), (GAME, 'Alice', 0b101))

    def test_another_seeds_save_is_never_read(self):
        path = os.path.join(self.save_dir, 'progress.sav')
        with open(path, 'wb') as stream:
            stream.write(make_save(bools={'RandoAP_Seed_other': True, 'Gift_Got': True}, bool64=[777]))
        srv, url = self.server()
        game = FakeGame(marker=False, snapshot_bools={'Gift_Got': True})
        s = self.session(url, game=game)
        self.assertTrue(wait(lambda: s.summary()['connected']))
        time.sleep(0.5)
        self.assertEqual(srv.checked_locations, set())
        self.assertIn('no save of this seed', s.summary()['save'])

    def test_live_game_checks(self):
        srv, url = self.server()
        game = FakeGame(snapshot_bools={'Gift_Got': True}, bool64={777: True})
        s = self.session(url, game=game)
        self.assertTrue(wait(lambda: srv.checked_locations >= {101, 102}))
        self.assertIn('a save of this seed is loaded', s.summary()['game'])

    # Items in
    def test_items_in_order_and_reconnect_never_redelivers(self):
        self.write_save()
        srv, url = self.server(items=[{'item': 77, 'location': 2000, 'player': 2, 'flags': 1},
                                      {'item': 79, 'location': -2, 'player': 0, 'flags': 0}])
        game = FakeGame()
        s = self.session(url, game=game)
        self.assertTrue(wait(lambda: game.given == [5, 3]), game.given)
        srv.send_item(78, from_player=2, location=2000, flags=1)
        self.assertTrue(wait(lambda: game.given == [5, 3, 9]), game.given)
        connects = srv.connects
        srv.drop_clients()
        self.assertTrue(wait(lambda: srv.connects > connects and s.summary()['connected']))
        time.sleep(0.4)
        self.assertEqual(game.given, [5, 3, 9])                    # Replaying the list gives no extra items.
        srv.send_item(77, from_player=2, location=2001)
        self.assertTrue(wait(lambda: game.given == [5, 3, 9, 5]), game.given)
        kinds = [e['kind'] for e in s.events()]
        self.assertEqual(kinds.count('delivered'), 4)

    def test_queue_while_the_game_is_not_running(self):
        srv, url = self.server(items=[{'item': 77, 'location': 2000, 'player': 2, 'flags': 1}])
        game = FakeGame()
        game.reachable = False
        s = self.session(url, game=game)
        self.assertTrue(wait(lambda: 'not reachable' in s.summary()['delivery']))
        self.assertEqual(game.writes, [])
        game.reachable = True
        self.assertTrue(wait(lambda: game.given == [5]))

    def test_menu_open_waits(self):
        srv, url = self.server(items=[{'item': 77, 'location': 2000, 'player': 2, 'flags': 1}])
        game = FakeGame()
        game.paused = True
        s = self.session(url, game=game)
        self.assertTrue(wait(lambda: 'waiting for the game' in s.summary()['delivery']))
        self.assertEqual(game.given, [])
        game.paused = False
        self.assertTrue(wait(lambda: game.given == [5]))

    # Refusals and chat
    def test_wrong_seed_is_refused(self):
        srv, url = self.server(slot_data={'seed': 'another', 'mailbox_version': 1})
        s = self.session(url)
        self.assertTrue(wait(lambda: s.summary()['fatal']))
        self.assertIn('another seed', s.summary()['status'])

    def test_wrong_password_is_fatal(self):
        srv, url = self.server(password='secret')
        s = self.session(url, password='nope')
        self.assertTrue(wait(lambda: s.summary()['fatal']))
        self.assertIn('InvalidPassword', s.summary()['status'])
        s2 = self.session(url, password='secret')
        self.assertTrue(wait(lambda: s2.summary()['connected']))

    def test_unknown_slot_is_fatal(self):
        srv, url = self.server(slot_name='Somebody')
        s = self.session(url)
        self.assertTrue(wait(lambda: s.summary()['fatal']))
        self.assertIn('InvalidSlot', s.summary()['status'])

    def test_chat_and_names(self):
        srv, url = self.server()
        s = self.session(url)
        self.assertTrue(wait(lambda: s.summary()['connected']))
        s.say('hello world')
        self.assertTrue(wait(lambda: 'hello world' in srv.said))
        self.assertTrue(wait(lambda: any(e['kind'] == 'chat' and 'hello world' in e['text'] for e in s.events())))
        self.assertEqual(s.client.name('item', 1000, 2), 'Hammer')

    def test_datapackage_cached_by_checksum(self):
        srv, url = self.server()
        s = self.session(url)
        self.assertTrue(wait(lambda: s.summary()['connected']))
        self.assertTrue(srv.get_datapackage_requests)
        s.stop()
        srv2, url2 = self.server()
        s2 = self.session(url2)
        self.assertTrue(wait(lambda: s2.summary()['connected']))
        self.assertEqual(srv2.get_datapackage_requests, [])         # both games came from the cache
        self.assertEqual(s2.client.item_name(77), 'Bow')

    def test_address_without_scheme_falls_back_to_plain_ws_here(self):
        srv, url = self.server(password='secret')
        address = url.split('://', 1)[1]                          # "127.0.0.1:PORT", as a player types it
        s = self.session(address, password='secret')
        self.assertTrue(wait(lambda: s.summary()['connected']), s.summary()['status'])
        self.assertFalse(s.summary()['encrypted'])
        self.assertIn('not encrypted', s.summary()['status'])


if __name__ == '__main__':
    unittest.main()
