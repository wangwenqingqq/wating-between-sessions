#!/usr/bin/env python3
import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

from core.history_parser import import_history
from core.state_manager import StateManager
from core.store import Store


def running(store):
    try:
        data = json.loads((store.root / 'runtime.json').read_text())
        url, key = data['url'].split('/#')
        request = urllib.request.Request(url + '/api/state', headers={'Authorization': 'Bearer ' + key})
        with urllib.request.urlopen(request, timeout=1) as response:
            if response.status == 200:
                return data
    except (OSError, ValueError, KeyError):
        return None


def main():
    p = argparse.ArgumentParser(description='Local waiting panel; Python standard library only.')
    p.add_argument('--data-dir', type=Path)
    sub = p.add_subparsers(dest='command', required=True)
    for name in ['serve', 'start']:
        s = sub.add_parser(name)
        s.add_argument('--port', type=int, default=0, help='0 selects a free loopback port')
        s.add_argument('--watch-codex', action='store_true', help='Consent to read local rollout lifecycle metadata')
        s.add_argument('--codex-root', type=Path, default=Path.home() / '.codex/sessions')
        s.add_argument('--open', action='store_true')
    h = sub.add_parser('import-history')
    h.add_argument('--provider', choices=['codex', 'claude'], required=True)
    h.add_argument('--root', type=Path)
    h.add_argument('--limit', type=int, default=100)
    h.add_argument('--consent', action='store_true', help='Explicitly authorize local history analysis')
    sub.add_parser('open')
    sub.add_parser('status')
    sub.add_parser('stop')
    sub.add_parser('delete-history')
    d = sub.add_parser('simulate')
    d.add_argument('--seconds', type=float, default=8)
    args = p.parse_args()
    store = Store(args.data_dir)
    if args.command == 'start':
        existing = running(store)
        if existing:
            if args.open:
                webbrowser.open(existing['url'], new=2)
            print('Local waiting panel is already running.')
            return
        command = [sys.executable, str(Path(__file__).resolve()), '--data-dir', str(store.root),
                   'serve', '--port', str(args.port)]
        if args.watch_codex:
            command += ['--watch-codex', '--codex-root', str(args.codex_root)]
        with (store.root / 'service.log').open('a') as log:
            child = subprocess.Popen(command, stdout=log, stderr=log, stdin=subprocess.DEVNULL, start_new_session=True)
        for _ in range(30):
            if child.poll() is not None:
                p.error('Service could not start. See ' + str(store.root / 'service.log'))
            runtime = running(store)
            if runtime:
                if args.open:
                    webbrowser.open(runtime['url'], new=2)
                print('Local waiting panel started. PID ' + str(runtime['pid']) + '; loopback port ' + str(runtime['port']))
                return
            time.sleep(0.1)
        p.error('Service is not ready; inspect the local service log before retrying.')
    elif args.command == 'serve':
        from server import serve
        serve(store, args.port, args.codex_root if args.watch_codex else None, args.open)
    elif args.command == 'import-history':
        if not args.consent:
            p.error('Pass --consent to authorize reading the selected local history root.')
        if not 1 <= args.limit <= 10000:
            p.error('--limit must be between 1 and 10000')
        root = args.root or Path.home() / ('.codex/sessions' if args.provider == 'codex' else '.claude/projects')
        store.set('history_enabled', True)
        print(json.dumps(import_history(store, root, args.provider, args.limit), indent=2))
    elif args.command == 'open':
        runtime = running(store)
        if not runtime:
            p.error('Start the local service first.')
        webbrowser.open(runtime['url'], new=2)
    elif args.command == 'stop':
        runtime = running(store)
        if not runtime:
            print('No authenticated local waiting-panel service is running.')
            return
        url, key = runtime['url'].split('/#')
        request = urllib.request.Request(url + '/api/shutdown', data=b'{}', headers={'Authorization': 'Bearer ' + key})
        with urllib.request.urlopen(request, timeout=3) as response:
            print('Waiting-panel shutdown requested; no other process was signaled.')
    elif args.command == 'status':
        with store.connect() as db:
            count = db.execute('SELECT COUNT(*) FROM timeline').fetchone()[0]
        print(json.dumps(dict(events=count, history_enabled=store.get('history_enabled', False),
                              sessions=StateManager(store).snapshot()), indent=2))
    elif args.command == 'delete-history':
        store.clear_history()
        print('Derived history deleted and analysis disabled. Original sessions are unchanged.')
    elif args.command == 'simulate':
        manager = StateManager(store)
        sid = 'synthetic-demo'
        manager.apply(sid, 'demo', 'UserPromptSubmit')
        print('Synthetic turn started; this is not a real host acceptance test.', flush=True)
        time.sleep(max(0, args.seconds))
        manager.apply(sid, 'demo', 'Stop')
        print('Synthetic turn ended.')


if __name__ == '__main__':
    main()
