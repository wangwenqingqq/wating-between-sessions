import hmac
import json
import secrets
import signal
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from core.codex_watcher import CodexWatcher
from core.chronicles import load_chronicles
from core.history_parser import select_content, verify_evidence
from core.state_manager import StateManager


WEB = Path(__file__).parent / 'ui/web'


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, store, port=8765, watch_root=None):
        self.store, self.manager = store, StateManager(store)
        self.token = secrets.token_urlsafe(32)
        self.last_client = self.last_open = 0
        self.observation_started = time.time()
        self.watcher = CodexWatcher(self.manager, watch_root) if watch_root else None
        self.stopped = threading.Event()
        super().__init__(('127.0.0.1', port), Handler)
        self.base = 'http://127.0.0.1:' + str(self.server_port)
        self.panel_url = self.base + '/#' + self.token

    def tick(self):
        while not self.stopped.wait(0.5):
            try:
                if self.watcher:
                    self.watcher.poll()
                if self.manager.claim_open():
                    now = time.time()
                    if now - self.last_client > 10 and now - self.last_open > 10:
                        self.last_open = now
                        webbrowser.open(self.panel_url, new=2)
            except Exception as exc:
                # Do not log message content or raw hook payloads.
                print('Observer tick failed: ' + type(exc).__name__, flush=True)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def reply(self, status, data, content_type='application/json; charset=utf-8'):
        payload = json.dumps(data, ensure_ascii=False).encode() if isinstance(data, (dict, list)) else data
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        self.end_headers()
        self.wfile.write(payload)

    def allowed(self, auth=True):
        if self.headers.get('Host') != urlsplit(self.server.base).netloc:
            self.reply(403, {'error': 'Invalid host'})
            return False
        origin = self.headers.get('Origin')
        if origin and origin != self.server.base:
            self.reply(403, {'error': 'Cross-origin access denied'})
            return False
        supplied = self.headers.get('Authorization', '')
        if auth and not hmac.compare_digest(supplied.encode(), ('Bearer ' + self.server.token).encode()):
            self.reply(401, {'error': 'Open the panel using python3 demo/app.py open'})
            return False
        return True

    def do_GET(self):
        url = urlsplit(self.path)
        if not self.allowed(auth=url.path.startswith('/api/')):
            return
        if url.path in {'/', '/app.js', '/style.css'}:
            name = {'/': 'index.html', '/app.js': 'app.js', '/style.css': 'style.css'}[url.path]
            content_type = {'/': 'text/html; charset=utf-8', '/app.js': 'text/javascript; charset=utf-8', '/style.css': 'text/css; charset=utf-8'}[url.path]
            return self.reply(200, (WEB / name).read_bytes(), content_type)
        if url.path == '/health':
            return self.reply(200, {'ok': True, 'app': 'agent-waiting-experience'})
        if url.path == '/api/state':
            self.server.last_client = time.time()
            store = self.server.store
            query = parse_qs(url.query)
            try:
                after = int(query['after'][0]) if 'after' in query else None
            except (ValueError, TypeError):
                return self.reply(400, {'error': 'Invalid transition cursor'})
            with store.connect() as db:
                counts = db.execute('SELECT COUNT(*),COUNT(DISTINCT source_provider || source_session_id) FROM timeline').fetchone()
                months = [r[0] for r in db.execute('SELECT DISTINCT substr(date,1,7) FROM timeline ORDER BY 1 DESC')]
                latest = db.execute('SELECT COALESCE(MAX(id),0) FROM transitions').fetchone()[0]
                signals = [dict(row) for row in db.execute('''SELECT id AS transition_id,session_id AS id,turn_id,state
                    FROM transitions WHERE id>? AND timestamp>=? AND state IN ('COMPLETED','FAILED','WAITING_USER')
                    ORDER BY transition_id LIMIT 100''', (max(0, after), self.server.observation_started))] if after is not None else []
            return self.reply(200, dict(sessions=self.server.manager.snapshot(), events=counts[0],
                                       histories=counts[1], months=months, auto_show=store.get('auto_show', True),
                                       history_enabled=store.get('history_enabled', False),
                                       signals=signals, next_signal=signals[-1]['transition_id'] if signals else latest,
                                       adapter='codex-rollout-experimental' if self.server.watcher else 'hooks',
                                       watcher_errors=self.server.watcher.errors if self.server.watcher else 0))
        if url.path == '/api/events':
            q = parse_qs(url.query)
            return self.reply(200, select_content(self.server.store, q.get('mode', ['timeline'])[0],
                                                 q.get('month', [''])[0], q.get('topic', [''])[0]))
        if url.path == '/api/chronicles':
            q = parse_qs(url.query)
            try:
                data = load_chronicles(self.server.store, q.get('month', [''])[0], q.get('topic', [''])[0])
            except ValueError:
                return self.reply(404, {'error': 'Unknown chronicle topic'})
            return self.reply(200, data)
        self.reply(404, {'error': 'Not found'})

    def do_POST(self):
        if not self.allowed():
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 4096:
                return self.reply(413, {'error': 'Invalid body size'})
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError()
        except (ValueError, TypeError):
            return self.reply(400, {'error': 'Invalid JSON'})
        store = self.server.store
        if self.path == '/api/shutdown':
            self.reply(200, {'ok': True})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        if self.path == '/api/settings':
            for key in ['auto_show', 'history_enabled']:
                if key in body:
                    if not isinstance(body[key], bool):
                        return self.reply(400, {'error': 'Boolean required'})
                    store.set(key, body[key])
            return self.reply(200, {'ok': True})
        if self.path == '/api/delete-history':
            if body.get('confirm') != 'DELETE':
                return self.reply(400, {'error': 'Confirmation required'})
            store.clear_history()
            return self.reply(200, {'ok': True})
        if self.path in {'/api/source', '/api/read'}:
            if not store.get('history_enabled', False):
                return self.reply(403, {'error': 'History disabled'})
            event_id = body.get('event_id')
            if not isinstance(event_id, str):
                return self.reply(400, {'error': 'Invalid event ID'})
            with store.connect() as db:
                row = db.execute('SELECT * FROM timeline WHERE event_id=?', (event_id,)).fetchone()
                if row and self.path == '/api/read':
                    db.execute('UPDATE timeline SET read_at=? WHERE event_id=?', (time.time(), event_id))
            if not row:
                return self.reply(404, {'error': 'No such event'})
            event = dict(row)
            if self.path == '/api/source':
                event['verified'] = verify_evidence(event)
            return self.reply(200, event)
        self.reply(404, {'error': 'Not found'})


def serve(store, port, watch_root=None, open_panel=False):
    # A per-data-directory lock prevents two launchers racing on separate ports.
    import fcntl
    with (store.root / 'server.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit('A waiting-panel service already uses this data directory.')
        server = Server(store, port, watch_root)
        runtime = store.root / 'runtime.json'
        runtime.write_text(json.dumps({'url': server.panel_url, 'pid': __import__('os').getpid(), 'port': server.server_port}))
        runtime.chmod(0o600)
        thread = threading.Thread(target=server.tick, daemon=True)
        thread.start()
        print('Waiting panel listening at ' + server.base + ' (access key stored locally)', flush=True)
        if open_panel:
            server.last_open = time.time()
            webbrowser.open(server.panel_url, new=2)

        def stop(signum, frame):
            threading.Thread(target=server.shutdown, daemon=True).start()

        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        try:
            server.serve_forever(poll_interval=0.3)
        finally:
            server.stopped.set()
            thread.join(timeout=5)
            server.server_close()
            runtime.unlink(missing_ok=True)
