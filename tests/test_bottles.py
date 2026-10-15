import json
import sqlite3
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'demo'))
from core.bottles import BottleBoard, BottleError
from core.store import Store
from server import Server


def note(field='gpu', text='A synthetic research concern, not a real personal story.'):
    return dict(field=field, body=text, consent=True, request_id=str(uuid.uuid4()))


class BottleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.pool = self.root / 'shared-bottles'
        self.a = BottleBoard(Store(self.root / 'a'), self.pool)
        self.b = BottleBoard(Store(self.root / 'b'), self.pool)
        self.c = BottleBoard(Store(self.root / 'c'), self.pool)

    def tearDown(self):
        self.tmp.cleanup()

    def join(self, board, fields=('gpu',)):
        return board.command('profile', dict(interests=list(fields), consent=True))

    def error(self, status, board, action, payload):
        with self.assertRaises(BottleError) as caught:
            board.command(action, payload)
        self.assertEqual(caught.exception.status, status)

    def test_no_implicit_identity_or_interest_sharing(self):
        status = self.a.status()
        self.assertFalse(status['joined'])
        self.assertEqual(status['interests'], [])
        self.assertFalse(self.pool.exists())
        self.assertIsNone(self.a.store.get('bottle_owner'))
        self.error(400, self.a, 'profile', dict(interests=['gpu']))
        self.error(400, self.a, 'profile', dict(interests=['gpu'], consent=1))
        self.error(403, self.a, 'pick', dict(field='gpu'))
        self.error(403, self.a, 'throw', note())
        for fields in [[], ['unknown'], ['gpu'] * 6, {}, [None], ['gpu', {}]]:
            self.error(400, self.a, 'profile', dict(interests=fields, consent=True))
        self.assertFalse(self.a.status()['joined'])

    def test_two_independent_profiles_exchange_only_in_selected_fields(self):
        self.join(self.a, ['gpu', 'ml']);self.join(self.b);self.join(self.c, ['bio'])
        bottle = self.a.command('throw', note())['bottle']
        self.assertIsNone(self.a.command('pick', dict(field='gpu'))['bottle'])
        picked = self.b.command('pick', dict(field='gpu'))['bottle']
        self.assertEqual(picked['id'], bottle['id']);self.assertFalse(picked['mine'])
        self.assertIsNone(self.c.command('pick', dict(field='bio'))['bottle'])
        self.error(403, self.c, 'pick', dict(field='gpu'))
        self.error(404, self.c, 'read', dict(bottle_id=bottle['id']))
        self.error(404, self.c, 'reply', dict(bottle_id=bottle['id'], body='Wrong field', consent=True, request_id=str(uuid.uuid4())))
        reply = dict(bottle_id=bottle['id'], body='A synthetic, supportive reply.', consent=True, request_id=str(uuid.uuid4()))
        self.b.command('reply', reply)
        read = self.a.command('read', dict(bottle_id=bottle['id']))['bottle']
        self.assertEqual(read['replies'][0]['body'], reply['body'])
        self.assertFalse(read['replies'][0]['mine']);self.assertFalse(read['replies'][0]['from_author'])
        mine = self.b.command('mine', {})
        self.assertEqual(mine['replies'][0]['bottle_id'], bottle['id'])
        self.assertEqual(mine['bottles'], [])
        self.assertIsNone(self.b.command('pick', dict(field='gpu', exclude=[bottle['id']]))['bottle'])

    def test_responses_never_expose_peer_identity_or_local_history(self):
        self.join(self.a);self.join(self.b)
        self.a.store.set('history_enabled', True)
        self.a.command('throw', note(text='**Only** the explicitly submitted text.'))
        picked = self.b.command('pick', dict(field='gpu'))
        encoded = json.dumps(picked)
        for secret in [self.a.store.get('bottle_owner'), self.b.store.get('bottle_owner'), str(self.root), 'source_path', 'source_session_id', 'interests']:
            self.assertNotIn(secret, encoded)
        with self.a.store.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM timeline').fetchone()[0], 0)
        self.assertTrue(self.a.store.get('history_enabled'))

    def test_post_and_reply_require_separate_consent_and_retries_are_idempotent(self):
        self.join(self.a);self.join(self.b)
        payload = note();missing = dict(payload);missing.pop('consent')
        self.error(400, self.a, 'throw', missing)
        first = self.a.command('throw', payload)['bottle']
        self.assertEqual(self.a.command('throw', payload)['bottle']['id'], first['id'])
        self.error(409, self.a, 'throw', dict(payload, body='Changed text'))
        reply = dict(bottle_id=first['id'], body='A reply', consent=True, request_id=str(uuid.uuid4()))
        self.error(400, self.b, 'reply', dict(reply, consent=False))
        once = self.b.command('reply', reply)['bottle']
        twice = self.b.command('reply', reply)['bottle']
        self.assertEqual(once['replies'], twice['replies'])
        self.error(409, self.b, 'reply', dict(reply, body='Another reply'))
        self.error(400, self.b, 'throw', dict(note(), owner=self.a.store.get('bottle_owner')))
        for value in ['', None, 'not-a-uuid']:
            self.error(400, self.a, 'throw', dict(note(), request_id=value))

    def test_lengths_control_characters_and_input_bounds(self):
        self.join(self.a)
        for text in ['', ' ', 'a' * 2001, 'line\x00secret', 1]:
            self.error(400, self.a, 'throw', note(text=text))
        self.a.command('throw', note(text='## Safe Markdown\n\n- one\n- two\t'))
        self.error(400, self.a, 'pick', dict(field='gpu', exclude=['not-a-uuid']))
        self.error(400, self.a, 'pick', dict(field='gpu', exclude=[str(uuid.uuid4())] * 101))
        self.error(404, self.a, 'unknown', {})

    def test_only_authors_can_delete_and_withdrawal_cascades_without_harming_peers(self):
        self.join(self.a);self.join(self.b)
        a = self.a.command('throw', note())['bottle']
        b = self.b.command('throw', note(text='Another synthetic note'))['bottle']
        reply_a = dict(bottle_id=b['id'], body='Reply A', consent=True, request_id=str(uuid.uuid4()))
        reply_b = dict(bottle_id=a['id'], body='Reply B', consent=True, request_id=str(uuid.uuid4()))
        mine_a = self.a.command('reply', reply_a)['bottle']['replies'][0]
        self.b.command('reply', reply_b)
        self.error(404, self.b, 'delete', dict(bottle_id=a['id'], confirm='DELETE'))
        self.error(404, self.b, 'delete-reply', dict(reply_id=mine_a['id'], confirm='DELETE'))
        self.error(400, self.a, 'withdraw', {})
        self.a.command('withdraw', dict(confirm='WITHDRAW'))
        self.assertFalse(self.a.status()['joined']);self.assertTrue(self.b.status()['joined'])
        self.error(404, self.b, 'read', dict(bottle_id=a['id']))
        self.assertEqual(self.b.command('read', dict(bottle_id=b['id']))['bottle']['replies'], [])
        self.assertEqual(len(self.b.command('mine', {})['bottles']), 1)
        with self.b.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM members').fetchone()[0], 1)

    def test_deleting_a_reply_and_bottle_requires_confirmation(self):
        self.join(self.a);self.join(self.b)
        bottle = self.a.command('throw', note())['bottle']
        response = self.b.command('reply', dict(bottle_id=bottle['id'], body='Temporary reply', consent=True, request_id=str(uuid.uuid4())))['bottle']['replies'][0]
        self.error(400, self.a, 'delete', dict(bottle_id=bottle['id']))
        self.error(400, self.b, 'delete-reply', dict(reply_id=response['id']))
        self.b.command('delete-reply', dict(reply_id=response['id'], confirm='DELETE'))
        self.assertEqual(self.b.command('mine', {})['replies'], [])
        self.a.command('delete', dict(bottle_id=bottle['id'], confirm='DELETE'))
        self.assertIsNone(self.b.command('pick', dict(field='gpu'))['bottle'])

    def test_removing_a_field_retracts_notes_and_replies_in_that_field(self):
        self.join(self.a, ['gpu', 'ml']);self.join(self.b)
        gpu = self.a.command('throw', note())['bottle']
        ml = self.a.command('throw', note('ml'))['bottle']
        peer = self.b.command('throw', note())['bottle']
        self.a.command('reply', dict(bottle_id=peer['id'], body='Temporary reply', consent=True, request_id=str(uuid.uuid4())))
        self.join(self.a, ['ml'])
        self.assertEqual([b['id'] for b in self.a.command('mine', {})['bottles']], [ml['id']])
        self.assertEqual(self.b.command('read', dict(bottle_id=peer['id']))['bottle']['replies'], [])
        self.error(404, self.b, 'read', dict(bottle_id=gpu['id']))
        self.error(403, self.a, 'pick', dict(field='gpu'))

    def test_private_pool_permissions_and_accidental_post_limit(self):
        self.join(self.a)
        self.assertEqual(self.pool.stat().st_mode & 0o777, 0o700)
        self.assertEqual(self.a.path.stat().st_mode & 0o777, 0o600)
        first = note()
        self.a.command('throw', first)
        for _ in range(19):
            self.a.command('throw', note())
        self.error(429, self.a, 'throw', note())
        self.a.command('throw', first)
        self.pool.chmod(0o755)
        try:
            with self.assertRaises(BottleError):
                self.a.status()
        finally:
            self.pool.chmod(0o700)

    def test_concurrent_peers_keep_isolated_ownership(self):
        self.join(self.a);self.join(self.b)
        with ThreadPoolExecutor(max_workers=4) as workers:
            results = list(workers.map(lambda i: (self.a if i % 2 else self.b).command('throw', note()), range(20)))
        self.assertEqual(len({r['bottle']['id'] for r in results}), 20)
        self.assertEqual(len(self.a.command('mine', {})['bottles']), 10)
        self.assertEqual(len(self.b.command('mine', {})['bottles']), 10)

    def test_retracted_submissions_cannot_be_resurrected_by_delayed_retries(self):
        self.join(self.a, ['gpu', 'ml']);self.join(self.b)
        payload = note();bottle = self.a.command('throw', payload)['bottle']
        reply = dict(bottle_id=bottle['id'], body='Retracted synthetic reply', consent=True, request_id=str(uuid.uuid4()))
        r = self.b.command('reply', reply)['bottle']['replies'][0]
        self.b.command('delete-reply', dict(reply_id=r['id'], confirm='DELETE'))
        self.error(410, self.b, 'reply', reply)
        self.a.command('delete', dict(bottle_id=bottle['id'], confirm='DELETE'))
        self.error(410, self.a, 'throw', payload)
        by_field = note();self.a.command('throw', by_field)
        self.join(self.a, ['ml']);self.join(self.a, ['gpu'])
        self.error(410, self.a, 'throw', by_field)
        by_profile = note();self.a.command('throw', by_profile)
        self.a.command('withdraw', dict(confirm='WITHDRAW'));self.join(self.a)
        self.error(410, self.a, 'throw', by_profile)
        with self.a.connect() as db:
            receipts = db.execute('SELECT * FROM consumed_requests').fetchall()
            self.assertEqual(len(receipts), 4)
            self.assertTrue(all(len(r.keys()) == 1 and len(r['digest']) == 64 for r in receipts))
            self.assertEqual(db.execute('SELECT COUNT(*) FROM bottles').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM replies').fetchone()[0], 0)

    def test_receipt_migration_backfills_active_notes_before_their_deletion(self):
        self.join(self.a)
        payload = note();bottle = self.a.command('throw', payload)['bottle']
        with self.a.connect() as db:
            db.execute('DROP TABLE consumed_requests')
        self.a.command('delete', dict(bottle_id=bottle['id'], confirm='DELETE'))
        self.error(410, self.a, 'throw', payload)

    def test_receipt_migration_is_atomic_against_other_writers(self):
        self.join(self.a);self.join(self.b)
        payload = note();bottle = self.b.command('throw', payload)['bottle']
        with self.a.connect() as db:
            db.execute('DROP TABLE consumed_requests');db.execute('PRAGMA user_version=0')
        entered, release = threading.Event(), threading.Event()
        receipt = self.a.receipt
        def paused(*args):
            entered.set()
            if not release.wait(3):raise RuntimeError('Migration test timed out')
            return receipt(*args)
        with patch.object(self.a, 'receipt', side_effect=paused), ThreadPoolExecutor(max_workers=1) as worker:
            result = worker.submit(self.a.status)
            try:
                self.assertTrue(entered.wait(2))
                with sqlite3.connect(self.a.path, timeout=.05) as other:
                    self.assertIsNone(other.execute("SELECT 1 FROM sqlite_master WHERE name='consumed_requests'").fetchone())
                    with self.assertRaises(sqlite3.OperationalError):other.execute('BEGIN IMMEDIATE')
            finally:
                release.set()
            result.result(timeout=3)
        self.b.command('delete', dict(bottle_id=bottle['id'], confirm='DELETE'))
        self.error(410, self.b, 'throw', payload)

    def test_failed_receipt_migration_rolls_back_and_can_recover(self):
        self.join(self.a);self.join(self.b)
        payload = note();bottle = self.b.command('throw', payload)['bottle']
        with self.a.connect() as db:
            db.execute('DROP TABLE consumed_requests');db.execute('PRAGMA user_version=0')
        with patch.object(self.a, 'receipt', side_effect=RuntimeError('Synthetic migration interruption')):
            with self.assertRaises(RuntimeError):self.a.status()
        with sqlite3.connect(self.a.path) as db:
            self.assertIsNone(db.execute("SELECT 1 FROM sqlite_master WHERE name='consumed_requests'").fetchone())
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM bottles').fetchone()[0], 1)
        self.b.command('delete', dict(bottle_id=bottle['id'], confirm='DELETE'))
        self.error(410, self.b, 'throw', payload)


class BottleHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory();root = Path(self.tmp.name)
        self.servers = [Server(Store(root / name), port=0, bottle_root=root / 'pool') for name in ['a', 'b']]
        self.threads = [threading.Thread(target=s.serve_forever, daemon=True) for s in self.servers]
        for t in self.threads:t.start()

    def tearDown(self):
        for s in self.servers:s.shutdown();s.server_close()
        for t in self.threads:t.join()
        self.tmp.cleanup()

    def request(self, n, path, data=None, auth=True, **headers):
        s = self.servers[n]
        if auth:headers['Authorization'] = 'Bearer ' + s.token
        req = urllib.request.Request(s.base + path, data=json.dumps(data, ensure_ascii=False).encode() if data is not None else None, headers=headers)
        try:return urllib.request.urlopen(req, timeout=4)
        except urllib.error.HTTPError as exc:return exc

    def test_authenticated_two_client_round_trip_and_ownership(self):
        self.assertEqual(self.request(0, '/api/bottles/status', auth=False).status, 401)
        self.assertEqual(self.request(0, '/api/bottles/status', Origin='https://example.invalid').status, 403)
        self.assertEqual(self.request(0, '/api/bottles/status', Host='example.invalid').status, 403)
        for n in [0, 1]:
            self.assertFalse(json.load(self.request(n, '/api/bottles/status'))['joined'])
            self.assertEqual(self.request(n, '/api/bottles/profile', dict(interests=['gpu'], consent=True)).status, 200)
        bottle = json.load(self.request(0, '/api/bottles/throw', note(text='## 联调测试\n\n这不是一条真实的科研烦恼。')))['bottle']
        picked = json.load(self.request(1, '/api/bottles/pick', dict(field='gpu')))['bottle']
        self.assertEqual(picked['id'], bottle['id'])
        self.assertEqual(self.request(1, '/api/bottles/reply', dict(bottle_id=bottle['id'], body='**联调回声**：两位用户确实互通。', consent=True, request_id=str(uuid.uuid4()))).status, 200)
        result = json.load(self.request(0, '/api/bottles/read', dict(bottle_id=bottle['id'])))['bottle']
        self.assertEqual(len(result['replies']), 1)
        self.assertEqual(self.request(1, '/api/bottles/delete', dict(bottle_id=bottle['id'], confirm='DELETE')).status, 404)
        self.assertEqual(self.request(1, '/api/bottles/status', auth=False, Authorization='Bearer ' + self.servers[0].token).status, 401)
        self.assertEqual(self.request(0, '/bottles.js', auth=False).status, 200)
        self.assertEqual(self.request(0, '/bottles.db', auth=False).status, 404)
        self.assertEqual(self.request(0, '/api/bottles/unknown', {}).status, 404)
        self.assertEqual(json.load(self.request(0, '/api/state'))['events'], 0)

    def test_consent_and_wire_payload_bounds(self):
        self.assertEqual(self.request(0, '/api/bottles/profile', dict(interests=['gpu'])).status, 400)
        self.request(0, '/api/bottles/profile', dict(interests=['gpu'], consent=True))
        self.assertEqual(self.request(0, '/api/bottles/throw', note(text='测' * 2000)).status, 200)
        self.assertEqual(self.request(0, '/api/bottles/throw', note(text='x' * 17000)).status, 413)


if __name__ == '__main__':
    unittest.main()
