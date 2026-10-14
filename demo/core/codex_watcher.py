import json
import time
from datetime import datetime
from pathlib import Path


def last_boundary(stream, end):
    """Recover the latest lifecycle record before a tail, without parsing tool bodies."""
    position, carry = end, b''
    while position > 0:
        start = max(0, position - 65536)
        stream.seek(start)
        chunk = stream.read(position - start) + carry
        lines = chunk.splitlines(keepends=True)
        carry = lines.pop(0) if start and lines else b''
        record_end = start + len(chunk)
        for raw in reversed(lines):
            sequence = record_end
            record_end -= len(raw)
            if any(name in raw for name in [b'task_started', b'task_complete', b'turn_aborted']):
                try:
                    record = json.loads(raw)
                    payload = record.get('payload', {})
                    if record.get('type') == 'event_msg' and payload.get('type') in {'task_started', 'task_complete', 'turn_aborted'}:
                        return record, sequence
                except (ValueError, TypeError, AttributeError):
                    pass
        position = start
    return None


class CodexWatcher:
    """Read-only, best-effort adapter for local rollout JSONL; not a stable host API."""

    def __init__(self, manager, root):
        self.manager, self.root = manager, Path(root).expanduser()
        self.files = {}
        self.last_scan = float('-inf')
        self.errors = 0
        self.calls = {}

    def discover(self):
        if time.monotonic() - self.last_scan < 5:
            return
        self.last_scan = time.monotonic()
        for path in self.root.rglob('*.jsonl'):
            if path in self.files or path.is_symlink():
                continue
            stat = path.stat()
            if time.time() - stat.st_mtime > 86400:
                continue
            try:
                with path.open('rb') as f:
                    meta = json.loads(f.readline()).get('payload', {})
                    if not isinstance(meta, dict):
                        continue
                    source = meta.get('source', '')
                    if isinstance(source, dict) and 'subagent' in source:
                        continue
                    sid = meta.get('id', meta.get('session_id', path.stem))
                    offset = max(0, stat.st_size - 2 * 1024 ** 2)
                    if offset:
                        f.seek(offset)
                        f.readline()
                        offset = f.tell()
                        boundary = last_boundary(f, offset)
                        if boundary:
                            self.consume(boundary[0], str(sid), boundary[1])
                self.files[path] = [str(sid), offset, stat.st_ino]
            except (OSError, ValueError, TypeError, AttributeError):
                self.errors += 1

    def consume(self, record, sid, offset):
        p = record.get('payload', {})
        if not isinstance(p, dict):
            return
        event, tool = '', ''
        turn = p.get('turn_id')
        if record.get('type') == 'event_msg':
            event = {'task_started': 'UserPromptSubmit', 'task_complete': 'Stop',
                     'turn_aborted': 'Interrupt', 'error': 'StopFailure'}.get(p.get('type'), '')
        elif record.get('type') == 'response_item':
            kind = p.get('type', '')
            if kind in {'function_call', 'custom_tool_call'}:
                event, tool = 'PreToolUse', p.get('name', '').split('.')[-1]
                if tool == 'request_user_input':
                    self.calls[p.get('call_id')] = tool
            elif kind in {'function_call_output', 'custom_tool_call_output', 'message'}:
                event = 'PostToolUse' if self.calls.pop(p.get('call_id'), None) else 'Heartbeat'
        if event:
            try:
                stamp = datetime.fromisoformat(record['timestamp'].replace('Z', '+00:00')).timestamp()
            except (KeyError, ValueError, TypeError):
                return
            self.manager.apply(sid, 'codex', event, turn_id=turn, tool=tool,
                               sequence=offset, now=stamp)

    def poll(self):
        self.discover()
        for path, info in list(self.files.items()):
            sid, offset, inode = info
            try:
                stat = path.stat()
                if stat.st_ino != inode or stat.st_size < offset:
                    offset = 0
                    with self.manager.store.connect() as db:
                        db.execute('UPDATE sessions SET sequence=0 WHERE id=?', ('codex:' + sid,))
                if stat.st_size == offset:
                    continue
                with path.open('rb') as f:
                    f.seek(offset)
                    # Bound each tick so a busy rollout cannot starve UI delivery.
                    for _ in range(10000):
                        start = f.tell()
                        raw = f.readline()
                        if not raw or not raw.endswith(b'\n'):
                            offset = start
                            break
                        offset = f.tell()
                        try:
                            record = json.loads(raw)
                            if isinstance(record, dict):
                                self.consume(record, sid, offset)
                        except (ValueError, TypeError):
                            self.errors += 1
                self.files[path] = [sid, offset, stat.st_ino]
            except OSError:
                self.errors += 1
                self.files.pop(path, None)

