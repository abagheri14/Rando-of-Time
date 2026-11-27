"""The mailbox (delivery.py) against a simulated game: order, receipts, retries, pauses, reloads, unknown items."""
import unittest

from client import delivery as D

from .helpers import FakeGame

CODES = {'Bow': 5, 'Hookshot': 9, 'Boomerang': 3, 'Bomb Bag': 1000}


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def run(delivery, game, names, clock, steps=50, dt=0.25):
    for _ in range(steps):
        delivery.step(names)
        clock.now += dt


class PureHelpers(unittest.TestCase):
    def test_bits_and_number_round_trip(self):
        for value in (0, 1, 5, 15, 1023):
            values = dict(D.bits(value, D.CODE))
            self.assertEqual(D.number(values, D.CODE), value)
        self.assertIsNone(D.number({}, D.CODE))

    def test_signal_writes_order(self):
        writes = D.signal_writes(17, 9)
        names = [n for n, _ in writes]
        self.assertEqual(names, D.IDX + D.CODE + D.IDX + [D.SIGNAL])
        self.assertEqual(D.number(dict(writes[:4]), D.IDX), 18 & 15)     # invalidates first
        self.assertEqual(D.number(dict(writes[4:14]), D.CODE), 9)
        self.assertEqual(D.number(dict(writes[14:18]), D.IDX), 17 & 15)
        self.assertEqual(writes[-1], (D.SIGNAL, True))                   # Signal last
        with self.assertRaises(ValueError):
            D.signal_writes(0, 1024)

    def test_writable_is_only_the_client_keys(self):
        from client.savefile import murmur3
        self.assertEqual(len(D.WRITABLE), 15)
        for name in D.COUNT + ['RandoAP_Seed_x']:
            self.assertNotIn(murmur3(name), D.WRITABLE)


class Deliver(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.game = FakeGame()
        self.delivery = D.Delivery(self.game, 'K3yK3yK3y', CODES, clock=self.clock)

    def test_items_arrive_in_order_once(self):
        names = ['Bow', 'Hookshot', 'Boomerang']
        run(self.delivery, self.game, names, self.clock)
        self.assertEqual(self.game.given, [5, 9, 3])
        self.assertEqual(self.game.count(), 3)
        self.assertEqual(self.delivery.waiting, 0)
        notes = self.delivery.mailbox.take_notes()
        self.assertEqual([i for kind, i in notes if kind == 'delivered'], [0, 1, 2])
        # After reconnect we get the same list again. Don't hand out duplicates.
        run(self.delivery, self.game, names, self.clock)
        self.assertEqual(self.game.given, [5, 9, 3])

    def test_new_item_later(self):
        run(self.delivery, self.game, ['Bow'], self.clock)
        run(self.delivery, self.game, ['Bow', 'Bomb Bag'], self.clock)
        self.assertEqual(self.game.given, [5, 1000])

    def test_nothing_without_the_marker(self):
        self.game.bools[self.game.marker_name] = False
        run(self.delivery, self.game, ['Bow'], self.clock)
        self.assertEqual(self.game.writes, [])
        self.assertIn('no save of this seed', self.delivery.status)

    def test_nothing_without_a_seed_key(self):
        delivery = D.Delivery(self.game, None, CODES, clock=self.clock)
        run(delivery, self.game, ['Bow'], self.clock)
        self.assertEqual(self.game.writes, [])

    def test_game_without_mailbox(self):
        class Bare:
            def read_bools(self, names):
                return {n: None for n in names}

            def write_bools(self, pairs):
                raise AssertionError('must not write')
        delivery = D.Delivery(Bare(), 'K3yK3yK3y', CODES, clock=self.clock)
        self.assertIsNone(delivery.step(['Bow']))
        self.assertIn('no mailbox', delivery.status)

    def test_paused_game_is_waited_for_without_retries(self):
        self.game.paused = True
        run(self.delivery, self.game, ['Bow'], self.clock, steps=200)     # 50 s in a menu
        self.assertEqual(self.delivery.mailbox.signals, 1)
        self.assertEqual(self.game.given, [])
        self.game.paused = False
        run(self.delivery, self.game, ['Bow'], self.clock)
        self.assertEqual(self.game.given, [5])

    def test_dropped_event_is_retried_after_8_seconds(self):
        self.game.drop = 1
        self.delivery.step(['Bow'])                       # signal 1
        self.clock.now += 0.25
        self.delivery.step(['Bow'])                       # the game took it and dropped it
        for _ in range(int(D.RETRY_SECONDS / 0.25) - 2):
            self.clock.now += 0.25
            self.delivery.step(['Bow'])
        self.assertEqual(self.delivery.mailbox.signals, 1)   # not yet
        run(self.delivery, self.game, ['Bow'], self.clock, steps=12)
        self.assertEqual(self.game.given, [5])
        self.assertEqual(self.delivery.mailbox.signals, 0)   # next item (none) after the receipt
        self.assertIn(('retry', 0), self.delivery.mailbox.take_notes())

    def test_set_aside_after_5_signals(self):
        self.game.drop = 10 ** 6
        run(self.delivery, self.game, ['Bow'], self.clock, steps=int(6 * D.RETRY_SECONDS / 0.25))
        notes = self.delivery.mailbox.take_notes()
        self.assertIn(('aside', 0), notes)
        self.assertEqual(sum(1 for kind, _ in notes if kind == 'retry'), D.MAX_SIGNALS - 1)
        writes_before = len(self.game.writes)
        run(self.delivery, self.game, ['Bow'], self.clock, steps=int((D.ASIDE_SECONDS - 15) / 0.25))
        self.assertEqual(len(self.game.writes), writes_before)          # quiet while aside
        self.game.drop = 0
        run(self.delivery, self.game, ['Bow'], self.clock, steps=int(25 / 0.25))
        self.assertEqual(self.game.given, [5])

    def test_older_save_gets_the_lost_items_again(self):
        run(self.delivery, self.game, ['Bow', 'Hookshot'], self.clock)
        self.game.set_count(1)                            # the player reloads a save made after the Bow
        run(self.delivery, self.game, ['Bow', 'Hookshot'], self.clock)
        self.assertEqual(self.game.given, [5, 9, 9])
        self.assertEqual(self.game.count(), 2)

    def test_unknown_name_waits_unknown_code_counts_as_nothing(self):
        run(self.delivery, self.game, [None], self.clock)
        self.assertEqual(self.game.writes, [])            # never guess before the DataPackage names it
        run(self.delivery, self.game, ['Some Future Item', 'Bow'], self.clock)
        self.assertEqual(self.game.given, [0, 5])
        self.assertIn(('no_code', 0), self.delivery.mailbox.take_notes())

    def test_stale_idx_is_harmless(self):
        # a Signal left over with a wrong Idx: the game ignores it, the client retries with the right one
        self.game.bools[D.SIGNAL] = True
        for name, value in D.bits(7, D.IDX):
            self.game.bools[name] = value
        run(self.delivery, self.game, ['Bow'], self.clock, steps=80)
        self.assertEqual(self.game.given, [5])

    def test_game_not_running_raises_for_the_session(self):
        from client.live_memory import LiveUnavailable
        self.game.reachable = False
        with self.assertRaises(LiveUnavailable):
            self.delivery.step(['Bow'])


class Codes(unittest.TestCase):
    def test_load_codes_missing(self):
        self.assertEqual(D.load_codes('Z:/no/such/folder'), ({}, None))

    def test_load_codes(self):
        import json
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            with open(os.path.join(folder, 'mailbox.json'), 'w', encoding='utf-8') as stream:
                json.dump({'mailbox_version': 1, 'codes': {'Bow': 5}}, stream)
            self.assertEqual(D.load_codes(folder), ({'Bow': 5}, 1))


if __name__ == '__main__':
    unittest.main()
