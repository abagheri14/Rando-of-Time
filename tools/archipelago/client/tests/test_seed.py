"""The save reader, the seed's check flags, the seed marker, the goal and the save finder."""
import json
import os
import tempfile
import time
import unittest

from client import goal as G
from client import savefile as S
from client.seed import Seed, SeedError, tracker_marks
from client.session import SaveFinder

from .helpers import make_save, write_seed

LOCATIONS = {'KF Chest': 101, 'KF Pot': 102, 'KF Gift': 103, 'KF Foreign Chest': 104, 'No Flag': 105}
CHECKS = [
    {'name': 'KF Chest', 'kind': 'chest', 'flags': [{'t': 'b64', 'h': str(0x1234567890ABCDEF)}]},
    {'name': 'KF Pot', 'kind': 'pot', 'flags': [{'t': 'bit', 'a': 'RandoChecked', 'i': 33}]},
    {'name': 'KF Gift', 'kind': 'npc', 'flags': [{'t': 'bool', 'n': 'Gift_Got'}]},
    {'name': 'KF Foreign Chest', 'kind': 'chest', 'flags': []},
    {'name': 'No Flag', 'kind': 'npc', 'flags': []},
    {'name': 'Not In AP', 'kind': 'pot', 'flags': [{'t': 'bool', 'n': 'Other'}]},
]
MARKER = 'RandoAP_Seed_K3yK3yK3y'


class SaveReader(unittest.TestCase):
    def test_murmur3_known_values(self):
        self.assertEqual(S.murmur3('Sequence_IsChildhood'), 0xCEA220D3)
        self.assertEqual(S.murmur3(''), 0)

    def test_decode(self):
        data = make_save(bools={'A': True, 'B': False}, ints={'N': -3}, enums={'Step_Defeat_Ganon': 'Ready'},
                         arrays={'RandoChecked': [i == 33 or i == 0 for i in range(70)]}, bool64=[5, 3])
        save = S.SaveFile(data)
        self.assertIs(save.bool('A'), True)
        self.assertIs(save.bool('B'), False)
        self.assertIsNone(save.bool('C'))
        self.assertEqual(save.int('N'), -3)
        self.assertEqual(save.enum('Step_Defeat_Ganon'), S.murmur3('Ready'))
        self.assertIs(save.bit('RandoChecked', 33), True)
        self.assertIs(save.bit('RandoChecked', 0), True)
        self.assertIs(save.bit('RandoChecked', 34), False)
        self.assertIsNone(save.bit('RandoChecked', 70))     # past the array
        self.assertIsNone(save.bit('Missing', 0))
        self.assertEqual(save.bool64, {3, 5})

    def test_rejects_garbage(self):
        for data in (b'', b'\0' * 64, b'\x04\x03\x02\x01' + b'\0' * 60):
            with self.assertRaises(S.SaveError):
                S.SaveFile(data)

    def test_load_and_find(self):
        with tempfile.TemporaryDirectory() as root:
            for slot, age in (('slot_00', 100), ('slot_01', 50)):
                os.makedirs(os.path.join(root, 'acct', slot))
                path = os.path.join(root, 'acct', slot, 'progress.sav')
                with open(path, 'wb') as stream:
                    stream.write(make_save(bools={'A': True}))
                os.utime(path, (time.time() - age, time.time() - age))
            found = S.find_saves(root)
            self.assertEqual([os.path.basename(os.path.dirname(p)) for p in found], ['slot_01', 'slot_00'])
            self.assertEqual(len(S.find_saves(root, 'slot_00')), 1)
            self.assertIs(S.load(found[0]).bool('A'), True)
            with open(found[0], 'wb') as stream:
                stream.write(b'junk')
            with self.assertRaises(S.SaveError):
                S.load(found[0], attempts=1)


class SeedChecks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = os.path.join(self.tmp.name, 'OUT')
        write_seed(self.folder, LOCATIONS, CHECKS, foreign={'KF Foreign Chest': {'item': 'Hammer', 'player': 2}})
        self.seed = Seed(self.folder)

    def tearDown(self):
        self.tmp.cleanup()

    def test_identity(self):
        s = self.seed
        self.assertEqual((s.game, s.slot_name, s.seed, s.seed_key, s.items_handling),
                         ('Rando of Time', 'Alice', '12345', 'K3yK3yK3y', 0b101))
        self.assertEqual(s.marker, S.murmur3(MARKER))
        self.assertIsInstance(s.goal, G.GanonGoal)

    def test_done_from_each_flag_kind(self):
        empty = S.SaveFile(make_save(bools={MARKER: True}))
        self.assertEqual(self.seed.done_locations(empty), set())
        save = S.SaveFile(make_save(
            bools={MARKER: True, 'Gift_Got': True, 'Other': True, 'RandoAP_Found_104': True},
            arrays={'RandoChecked': [i == 33 for i in range(40)]}, bool64=[0x1234567890ABCDEF]))
        # 'Not In AP' has no location id: never sent
        self.assertEqual(self.seed.done_locations(save), {101, 102, 103, 104})

    def test_found_flag_on_any_location(self):
        # an own-item spot without a save flag of its own, which a patch may mark with RandoAP_Found_<id>
        save = S.SaveFile(make_save(bools={MARKER: True, 'RandoAP_Found_105': True}))
        self.assertEqual(self.seed.done_locations(save), {105})

    def test_live_flags(self):
        live = {'bool': {S.murmur3('Gift_Got'): True}, 'bool64': {0x1234567890ABCDEF: True},
                'bool64_complete': True}
        self.assertEqual(self.seed.done_locations(None, live), {101, 103})
        live['bool64_complete'] = False
        self.assertEqual(self.seed.done_locations(None, live), {103})

    def test_marks(self):
        self.assertEqual(self.seed.done_locations(None, None, ['No Flag', 'Unknown']), {105})
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, 'settings.json')
            with open(path, 'w', encoding='utf-8-sig') as stream:
                json.dump({'Manual': {'12345': ['No Flag'], 'other': ['KF Chest']}}, stream)
            self.assertEqual(tracker_marks('12345', path), ['No Flag'])
            self.assertEqual(tracker_marks('nope', path), [])
        self.assertEqual(tracker_marks('12345', 'Z:/missing.json'), [])

    def test_owns(self):
        self.assertTrue(self.seed.owns(S.SaveFile(make_save(bools={MARKER: True}))))
        self.assertFalse(self.seed.owns(S.SaveFile(make_save(bools={'RandoAP_Seed_other': True}))))
        self.assertFalse(self.seed.owns(None))
        self.assertTrue(self.seed.owns({'bool': {S.murmur3(MARKER): True}}))
        self.assertFalse(self.seed.owns({'bool': {}}))

    def test_without_seed_key_everything_counts(self):
        folder = os.path.join(self.tmp.name, 'OLD')
        write_seed(folder, LOCATIONS, CHECKS, seed_key=None)
        seed = Seed(folder)
        self.assertIsNone(seed.marker)
        self.assertTrue(seed.owns(None))

    def test_errors(self):
        with self.assertRaises(SeedError):
            Seed(self.tmp.name)                            # no ap.json
        os.remove(os.path.join(self.folder, 'tracker.json'))
        with self.assertRaises(SeedError):
            Seed(self.folder)


class Goals(unittest.TestCase):
    def test_ganon(self):
        goal = G.GanonGoal()
        self.assertFalse(goal.reached(S.SaveFile(make_save(enums={'Step_Defeat_Ganon': 'Ready'}))))
        self.assertTrue(goal.reached(S.SaveFile(make_save(enums={'Step_Defeat_Ganon': 'Complete'}))))
        self.assertTrue(goal.reached(S.SaveFile(make_save(bools={G.ENDING_PLAYED: True}))))
        self.assertTrue(goal.reached(None, {'bool': {S.murmur3(G.TO_TITLE_FROM_CLEAR): True}}))
        self.assertTrue(goal.reached(None, {'bool': {S.murmur3(G.ENDING_PLAYED): True}}))
        self.assertFalse(goal.reached(None, {'bool': {S.murmur3(G.ENDING_PLAYED): False}}))
        self.assertFalse(goal.reached(None, None))

    def test_triforce_from_plan_and_settings(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertIsInstance(G.seed_goal(folder), G.GanonGoal)
            with open(os.path.join(folder, 'spoiler.json'), 'w', encoding='utf-8') as stream:
                json.dump({'settings': {'triforce_hunt': True, 'triforce_goal_per_world': 7}}, stream)
            goal = G.seed_goal(folder)
            self.assertEqual((goal.kind, goal.goal), ('triforce', 7))
            with open(os.path.join(folder, 'plan.json'), 'w', encoding='utf-8') as stream:
                json.dump({'_gaps': {'triforce': {'count': 30, 'goal': 20, 'counter': 'Rando_TriforcePieceNum'}}},
                          stream)
            goal = G.seed_goal(folder)
            self.assertEqual(goal.goal, 20)
            self.assertFalse(goal.reached(S.SaveFile(make_save(ints={'Rando_TriforcePieceNum': 19}))))
            self.assertTrue(goal.reached(S.SaveFile(make_save(ints={'Rando_TriforcePieceNum': 20}))))
            # Ganon's step doesn't count in a Triforce Hunt
            self.assertFalse(goal.reached(S.SaveFile(make_save(enums={'Step_Defeat_Ganon': 'Complete'}))))
            # ap.json's "goal" wins over the folder's files
            self.assertIsInstance(G.seed_goal(folder, {'kind': 'ganon'}), G.GanonGoal)
            declared = G.seed_goal(folder, {'kind': 'triforce_hunt', 'count': 12})
            self.assertEqual((declared.kind, declared.goal), ('triforce', 12))
            self.assertEqual(G.seed_goal(folder, {'kind': 'unknown'}).goal, 20)    # unknown kind: the files decide


class FindTheSeedsSave(unittest.TestCase):
    def test_newest_save_of_this_seed_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = os.path.join(tmp, 'OUT')
            write_seed(folder, LOCATIONS, CHECKS)
            seed = Seed(folder)
            root = os.path.join(tmp, 'save', 'acct')
            files = {}
            for slot, marker, age in (('slot_00', True, 300), ('slot_01', False, 10), ('slot_02', True, 100)):
                os.makedirs(os.path.join(root, slot))
                path = files[slot] = os.path.join(root, slot, 'progress.sav')
                with open(path, 'wb') as stream:
                    stream.write(make_save(bools={MARKER: marker, 'Slot': slot == 'slot_02'}))
                os.utime(path, (time.time() - age, time.time() - age))
            finder = SaveFinder(seed, os.path.join(tmp, 'save'))
            save = finder.poll()
            self.assertEqual(os.path.basename(os.path.dirname(save.path)), 'slot_02')   # slot_01 is another seed's
            # caught mid-write: the last good read stays
            with open(files['slot_02'], 'wb') as stream:
                stream.write(b'half')
            self.assertEqual(os.path.basename(os.path.dirname(finder.poll().path)), 'slot_02')
            empty = SaveFinder(seed, os.path.join(tmp, 'nothing'))
            self.assertIsNone(empty.poll())
            self.assertIn('no save found', empty.error)


if __name__ == '__main__':
    unittest.main()
