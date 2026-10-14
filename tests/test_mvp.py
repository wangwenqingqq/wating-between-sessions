import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'demo'))
from core.codex_watcher import CodexWatcher
from core.history_parser import import_history, parse_session, select_content, verify_evidence
from core.state_manager import StateManager
from core.store import Store
from server import Server


def codex_message(text, role='user', stamp='2026-10-12T08:00:00Z'):
    return dict(timestamp=stamp, type='response_item', payload=dict(type='message', role=role,
                phase='final_answer' if role == 'assistant' else None, content=[dict(type='input_text', text=text)]))


class MVPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = Store(self.root / 'data')
        self.manager = StateManager(self.store)

    def tearDown(self):
        self.tmp.cleanup()

    def row(self):
        return self.manager.snapshot(now=110)[0]

    def test_five_second_delay_and_single_open(self):
        self.manager.apply('s', 'claude', 'UserPromptSubmit', now=100)
        self.assertFalse(self.manager.claim_open(104.99))
        self.assertTrue(self.manager.claim_open(105))
        self.assertFalse(self.manager.claim_open(106))
        for _ in range(50):
            self.manager.apply('s', 'claude', 'PostToolUse', now=107)
        self.assertEqual(self.row()['started'], 100)
        self.assertFalse(self.manager.claim_open(110))

    def test_disable_auto(self):
        self.store.set('auto_show', False)
        self.manager.apply('s', 'claude', 'UserPromptSubmit', now=100)
        self.assertFalse(self.manager.claim_open(110))

    def test_open_claim_rechecks_turn_and_terminal_state(self):
        snapshot = self.manager.snapshot
        for next_event in ['Stop', 'UserPromptSubmit']:
            self.manager.apply('s', 'claude', 'UserPromptSubmit', now=100)
            def raced(now):
                rows = snapshot(now)
                self.manager.apply('s', 'claude', next_event, now=110)
                return rows
            self.manager.snapshot = raced
            self.assertFalse(self.manager.claim_open(110))
            self.manager.snapshot = snapshot

    def test_permissions_and_recoverable_tool_failure(self):
        for event, expected in [('UserPromptSubmit', 'WORKING'), ('PermissionRequest', 'WAITING_USER'),
                                ('PostToolUse', 'WORKING'), ('PostToolUseFailure', 'WORKING'),
                                ('Stop', 'COMPLETED')]:
            self.manager.apply('s', 'claude', event, now=100)
            self.assertEqual(self.row()['state'], expected)

    def test_question_and_new_turn(self):
        self.manager.apply('s', 'claude', 'UserPromptSubmit', now=100, turn_id='a')
        self.manager.apply('s', 'claude', 'PreToolUse', now=101, tool='AskUserQuestion')
        self.assertEqual(self.row()['state'], 'WAITING_USER')
        self.manager.apply('s', 'claude', 'UserPromptSubmit', now=102, turn_id='b')
        self.manager.apply('s', 'claude', 'Stop', now=103, turn_id='a')
        self.assertEqual(self.row()['state'], 'WORKING')
        self.manager.apply('s', 'claude', 'Stop', now=104, turn_id='b')
        self.assertEqual(self.row()['state'], 'COMPLETED')

    def test_concurrent_sessions_and_providers(self):
        for provider in ['claude', 'codex']:
            self.manager.apply('same', provider, 'UserPromptSubmit', now=100)
        self.manager.apply('same', 'claude', 'StopFailure', now=105)
        states = {r['provider']: r['state'] for r in self.manager.snapshot(106)}
        self.assertEqual(states, dict(claude='FAILED', codex='WORKING'))

    def test_out_of_order_and_duplicate_events(self):
        self.manager.apply('s', 'codex', 'UserPromptSubmit', turn_id='a', sequence=10, now=100)
        self.manager.apply('s', 'codex', 'Stop', turn_id='a', sequence=20, now=101)
        self.manager.apply('s', 'codex', 'UserPromptSubmit', turn_id='a', sequence=10, now=102)
        self.manager.apply('s', 'codex', 'PreToolUse', sequence=30, now=103)
        self.assertEqual(self.row()['state'], 'COMPLETED')

    def test_project_names_are_isolated_persisted_and_backfilled_without_replay(self):
        self.manager.apply('a', 'codex', 'UserPromptSubmit', now=100, sequence=10)
        self.manager.apply('a', 'codex', 'Stop', now=105, sequence=20)
        self.manager.apply('a', 'codex', 'Stop', now=105, sequence=20, project_name='Project Alpha')
        self.manager.apply('b', 'codex', 'UserPromptSubmit', now=106, project_name='Project Beta')
        self.manager.apply('b', 'codex', 'Heartbeat', now=107)
        rows = {r['id']: r for r in StateManager(Store(self.store.root)).snapshot(110)}
        self.assertEqual(rows['codex:a']['project_name'], 'Project Alpha')
        self.assertEqual(rows['codex:a']['state'], 'COMPLETED')
        self.assertEqual(rows['codex:b']['project_name'], 'Project Beta')
        self.assertEqual(rows['codex:b']['started'], 106)
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM transitions').fetchone()[0], 3)

    def test_project_name_schema_migration_preserves_old_state(self):
        root = self.root / 'legacy';root.mkdir()
        with sqlite3.connect(root / 'timeline.db') as db:
            db.execute('''CREATE TABLE sessions (id TEXT PRIMARY KEY, provider TEXT, state TEXT,
                turn_id TEXT, started REAL, updated REAL, event TEXT, detail TEXT,
                opened_turn TEXT, sequence REAL)''')
            db.execute("INSERT INTO sessions VALUES ('codex:old','codex','COMPLETED','turn',100,105,'Stop','done','turn',20)")
        manager = StateManager(Store(root))
        manager.apply('old', 'codex', 'Stop', sequence=20, project_name='Legacy Project')
        row = manager.snapshot(110)[0]
        self.assertEqual((row['state'], row['started'], row['project_name']), ('COMPLETED', 100, 'Legacy Project'))

    def test_stale_is_unknown_not_failed(self):
        self.manager.apply('s', 'claude', 'UserPromptSubmit', now=100)
        row = self.manager.snapshot(now=1100)[0]
        self.assertTrue(row['stale'])
        self.assertEqual(row['state'], 'WORKING')
        self.assertFalse(row['panel_due'])

    def test_session_exit_and_restart_persistence(self):
        self.manager.apply('s', 'claude', 'UserPromptSubmit', now=100)
        self.manager.apply('s', 'claude', 'SessionEnd', now=101)
        self.assertEqual(StateManager(Store(self.store.root)).snapshot(102)[0]['state'], 'FAILED')

    def history(self):
        path = self.root / 'sessions/s.jsonl'
        path.parent.mkdir()
        rows = [dict(type='session_meta', payload=dict(id='s', source='vscode')),
                codex_message('实现一个本地时间线，尚未解决重复弹窗问题'),
                codex_message('已实现本地时间线。', 'assistant'),
                codex_message('已实现本地时间线。', 'assistant')]
        path.write_text('\n'.join(json.dumps(r, ensure_ascii=False) for r in rows) + '\n')
        return path

    def test_import_consent_dedup_cache_and_incremental_update(self):
        path = self.history()
        with self.assertRaises(ValueError):
            import_history(self.store, path.parent, 'codex')
        self.store.set('history_enabled', True)
        report = import_history(self.store, path.parent, 'codex')
        self.assertEqual(report['imported'], 1)
        self.assertEqual(report['events'], 2)
        self.assertEqual(import_history(self.store, path.parent, 'codex')['cached'], 1)
        old = select_content(self.store)[0]
        with path.open('a') as f:
            f.write(json.dumps(codex_message('决定采用本地 SQLite')) + '\n')
        self.assertEqual(import_history(self.store, path.parent, 'codex')['events'], 3)
        self.assertTrue(verify_evidence(old))
        self.assertEqual(len(select_content(self.store, mode='discovery')), 1)

    def test_evidence_tampering_detected(self):
        path = self.history()
        event = next(e for e in parse_session(path, 'codex')[1] if e['kind'] == 'open_question')
        self.assertTrue(verify_evidence(event))
        path.write_text(path.read_text().replace('重复弹窗', '新的问题'))
        self.assertFalse(verify_evidence(event))

    def test_cache_is_provider_and_per_file_version_specific(self):
        path = self.history()
        self.store.set('history_enabled', True)
        self.assertEqual(import_history(self.store, path.parent, 'claude')['imported'], 0)
        self.assertEqual(import_history(self.store, path.parent, 'codex')['imported'], 1)
        other = path.parent / 't.jsonl'
        other.write_text(path.read_text().replace('"id": "s"', '"id": "t"'))
        import_history(self.store, path.parent, 'codex', limit=2)
        with self.store.connect() as db:
            db.execute('UPDATE imports SET extractor_version=0')
        self.assertEqual(import_history(self.store, path.parent, 'codex', limit=1)['imported'], 1)
        report = import_history(self.store, path.parent, 'codex', limit=2)
        self.assertEqual((report['imported'], report['cached']), (1, 1))

    def test_excludes_secrets_instructions_analysis_tools_and_subagents(self):
        path = self.root / 's.jsonl'
        rows = [codex_message('# AGENTS.md instructions\n<INSTRUCTIONS>secret instructions</INSTRUCTIONS>'),
                codex_message('api_key=sk-' + 'x' * 32),
                codex_message('登录用户 demo, pwd:ab'),
                codex_message('<timezone>Asia/Shanghai</timezone><filesystem>private config</filesystem></environment_context>'),
                dict(type='response_item', payload=dict(type='message', role='assistant', phase='analysis', content='private reasoning')),
                dict(type='response_item', payload=dict(type='function_call_output', output='private tool output')),
                codex_message('学习状态机原理')]
        path.write_text('\n'.join(json.dumps(r) for r in rows))
        events = parse_session(path, 'codex')[1]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['summary'], '学习状态机原理')
        path.write_text(json.dumps(dict(type='session_meta', payload=dict(source={'subagent': 'x'}))) + '\n' + json.dumps(codex_message('实现一个功能')))
        self.assertEqual(parse_session(path, 'codex')[1], [])

    def test_claude_parser(self):
        path = self.root / 'c.jsonl'
        path.write_text(json.dumps(dict(type='user', sessionId='c', timestamp='2026-10-12T08:00:00Z', message=dict(content='解释一个本地服务'))))
        sid, events = parse_session(path, 'claude')
        self.assertEqual(sid, 'c')
        self.assertEqual(events[0]['source_line'], 1)

    def test_delete_and_disable_do_not_modify_original(self):
        path = self.history()
        original = path.read_bytes()
        self.store.set('history_enabled', True)
        import_history(self.store, path.parent, 'codex')
        (self.store.root / 'human-review.csv').write_text('private excerpt')
        self.store.clear_history()
        self.assertFalse(self.store.get('history_enabled'))
        self.assertEqual(select_content(self.store), [])
        self.assertEqual(path.read_bytes(), original)
        self.assertFalse((self.store.root / 'human-review.csv').exists())
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM imports').fetchone()[0], 0)

    def test_watcher_partial_append_and_rotation(self):
        path = self.root / 'rollouts/s.jsonl';path.parent.mkdir()
        stamp = '2026-10-14T00:00:00Z'
        start = dict(type='event_msg', timestamp=stamp, payload=dict(type='task_started', turn_id='a'))
        stop = dict(type='event_msg', timestamp=stamp, payload=dict(type='task_complete', turn_id='a'))
        path.write_text(json.dumps(dict(type='session_meta', payload=dict(id='s', source='vscode'))) + '\n' + json.dumps(start) + '\n')
        watcher = CodexWatcher(self.manager, path.parent)
        watcher.poll()
        self.assertEqual(self.row()['state'], 'WORKING')
        with path.open('a') as f:f.write(json.dumps(stop))
        watcher.poll()
        self.assertEqual(self.row()['state'], 'WORKING')
        with path.open('a') as f:f.write('\n')
        watcher.poll()
        self.assertEqual(self.row()['state'], 'COMPLETED')
        start['payload']['turn_id'] = 'b'
        path.write_text(json.dumps(start) + '\n')
        watcher.poll()
        self.assertEqual(self.row()['state'], 'WORKING')

    def test_hook_is_nonblocking_and_has_no_permission_output(self):
        env = dict(os.environ, AWE_DATA_DIR=str(self.store.root))
        for data in [dict(session_id='s', hook_event_name='PermissionRequest'), {'bad': True}]:
            result = subprocess.run([sys.executable, str(ROOT / 'demo/hooks/lifecycle.py')],
                                    input=json.dumps(data), text=True, capture_output=True, env=env, timeout=4)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, '')

    def test_watcher_recovers_start_before_two_megabyte_tail(self):
        path = self.root / 'rollouts/s.jsonl';path.parent.mkdir()
        stamp = '2026-10-14T00:00:00Z'
        rows = [dict(type='session_meta', payload=dict(id='s', source='vscode')),
                dict(type='event_msg', timestamp=stamp, payload=dict(type='task_started', turn_id='a')),
                dict(type='response_item', payload=dict(type='function_call_output', output='x' * (3 * 1024 ** 2))),
                dict(type='response_item', timestamp=stamp, payload=dict(type='message', role='assistant'))]
        path.write_text('\n'.join(json.dumps(r) for r in rows) + '\n')
        watcher = CodexWatcher(self.manager, path.parent)
        watcher.poll()
        self.assertEqual(self.row()['state'], 'WORKING')

    def test_private_permissions(self):
        self.assertEqual(self.store.root.stat().st_mode & 0o777, 0o700)
        self.assertEqual(self.store.path.stat().st_mode & 0o777, 0o600)

    def test_watcher_uses_matching_title_with_directory_fallback(self):
        root = self.root / 'rollouts';root.mkdir()
        (self.root / 'session_index.jsonl').write_text(json.dumps({'id':'a','thread_name':'Named Project'}) + '\ninvalid\n')
        for sid in ['a', 'b']:
            rows = [dict(type='session_meta', payload=dict(id=sid, source='vscode', cwd=str(self.root / ('project-' + sid)))),
                    dict(type='event_msg', timestamp='2026-10-14T00:00:00Z', payload=dict(type='task_started', turn_id=sid))]
            (root / (sid + '.jsonl')).write_text('\n'.join(json.dumps(r) for r in rows) + '\n')
        CodexWatcher(self.manager, root).poll()
        rows = {r['id']:r for r in self.manager.snapshot(110)}
        self.assertEqual(rows['codex:a']['project_name'], 'Named Project')
        self.assertEqual(rows['codex:b']['project_name'], 'project-b')

    def test_hook_captures_directory_name_without_full_path(self):
        cwd = self.root / 'Hook Project'
        result = subprocess.run([sys.executable, str(ROOT / 'demo/hooks/lifecycle.py')],
                                input=json.dumps(dict(session_id='s', hook_event_name='SessionStart', cwd=str(cwd))),
                                text=True, capture_output=True, env=dict(os.environ, AWE_DATA_DIR=str(self.store.root)), timeout=4)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, '')
        self.assertEqual(self.row()['project_name'], 'Hook Project')
        self.assertNotIn(str(cwd), json.dumps(self.row()))


class HTTPTests(unittest.TestCase):
    def setUp(self):
        MVPTests.setUp(self)
        self.server = Server(self.store, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join()
        MVPTests.tearDown(self)

    def request(self, path, auth=True, data=None, **headers):
        if auth:headers['Authorization'] = 'Bearer ' + self.server.token
        req = urllib.request.Request(self.server.base + path, headers=headers,
                                     data=json.dumps(data).encode() if data is not None else None)
        try:
            return urllib.request.urlopen(req, timeout=3)
        except urllib.error.HTTPError as e:
            return e

    def test_http_auth_origin_host_and_static_allowlist(self):
        self.assertEqual(self.request('/api/state', auth=False).status, 401)
        self.assertEqual(self.request('/api/state', Origin='https://evil.invalid').status, 403)
        self.assertEqual(self.request('/api/state', Host='evil.invalid').status, 403)
        self.assertEqual(self.request('/../../etc/passwd').status, 404)
        response = self.request('/')
        self.assertEqual(response.status, 200)
        self.assertIn("frame-ancestors 'none'", response.headers['Content-Security-Policy'])
        self.assertEqual(self.request('/api/state').status, 200)

    def test_http_settings_and_delete(self):
        self.assertEqual(self.request('/api/settings', data={'auto_show': 'yes'}).status, 400)
        self.assertEqual(self.request('/api/settings', data={'auto_show': False}).status, 200)
        self.assertFalse(self.store.get('auto_show'))
        self.assertEqual(self.request('/api/delete-history', data={'confirm': 'no'}).status, 400)
        self.assertEqual(self.request('/api/delete-history', data={'confirm': 'DELETE'}).status, 200)

    def test_chronicles_auth_consent_and_topic_validation(self):
        self.assertEqual(self.request('/api/chronicles', auth=False).status, 401)
        self.assertEqual(self.request('/api/chronicles', Origin='https://evil.invalid').status, 403)
        self.assertEqual(json.load(self.request('/api/chronicles'))['stats']['events'], 0)
        path = MVPTests.history(self)
        self.store.set('history_enabled', True)
        import_history(self.store, path.parent, 'codex')
        result = json.load(self.request('/api/chronicles'))
        self.assertEqual(result['stats']['events'], 2)
        self.assertEqual(self.request('/api/chronicles?topic=not-real').status, 404)
        self.store.clear_history()
        self.assertEqual(json.load(self.request('/api/chronicles'))['topics'], [])

    def test_completion_feed_survives_a_new_turn_between_polls(self):
        start = json.load(self.request('/api/state'))['next_signal']
        now = self.server.observation_started
        self.manager.apply('s', 'claude', 'UserPromptSubmit', now=now + 1)
        self.manager.apply('s', 'claude', 'Stop', now=now + 2)
        self.manager.apply('s', 'claude', 'UserPromptSubmit', now=now + 3)
        result = json.load(self.request('/api/state?after=' + str(start)))
        self.assertEqual([r['state'] for r in result['signals']], ['COMPLETED'])
        self.assertEqual(result['sessions'][0]['state'], 'WORKING')
        again = json.load(self.request('/api/state?after=' + str(result['next_signal'])))
        self.assertEqual(again['signals'], [])

    def test_bootstrap_replay_is_not_a_live_completion_notice(self):
        cursor = json.load(self.request('/api/state'))['next_signal']
        self.manager.apply('old', 'codex', 'UserPromptSubmit', now=100)
        self.manager.apply('old', 'codex', 'Stop', now=110)
        replay = json.load(self.request('/api/state?after=' + str(cursor)))
        self.assertEqual(replay['signals'], [])
        now = self.server.observation_started
        self.manager.apply('live', 'codex', 'UserPromptSubmit', now=now + 1)
        self.manager.apply('live', 'codex', 'Stop', now=now + 2)
        live = json.load(self.request('/api/state?after=' + str(replay['next_signal'])))
        self.assertEqual([s['id'] for s in live['signals']], ['codex:live'])


if __name__ == '__main__':
    unittest.main()
