import hashlib
import json
import re
import shutil
import subprocess
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


EXTRACTOR_VERSION = 3
SENSITIVE = re.compile(r'(?i)(sk-[\w-]{16,}|gh[pousr]_[\w]{16,}|github_pat_[\w]+|'
                       r'-----BEGIN .*PRIVATE KEY|(?:api[_ -]?key|token|password|passwd|pwd|cookie|authorization|密码|口令)\s*[:=：]\s*\S+|'
                       r'https?://[^\s/]+:[^\s/]+@)')
NOISE = ('# AGENTS.md', '<environment_context>', '<INSTRUCTIONS>', '<permissions',
         '<external_', '<system', '<developer', '# Files mentioned by the user:')


def text_content(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return '\n'.join(p.get('text', '') for p in content
                         if isinstance(p, dict) and isinstance(p.get('text'), str)
                         and p.get('type') in {'text', 'input_text', 'output_text'})
    return ''


def message(record, provider):
    if provider == 'codex':
        p = record.get('payload', {})
        if not isinstance(p, dict):
            return None, ''
        if record.get('type') == 'response_item' and p.get('type') == 'message':
            role = p.get('role')
            if role == 'user' or (role == 'assistant' and p.get('phase') == 'final_answer'):
                return role, text_content(p.get('content'))
        if record.get('type') == 'event_msg' and p.get('type') == 'task_complete':
            return 'assistant', p.get('last_agent_message', '')
    elif provider == 'claude' and record.get('type') in {'user', 'assistant'} and not record.get('isSidechain'):
        p = record.get('message', {})
        if isinstance(p, dict) and not record.get('isApiErrorMessage'):
            return record['type'], text_content(p.get('content'))
    return None, ''


def excerpt(text):
    if not isinstance(text, str) or SENSITIVE.search(text):
        return ''
    if '## My request:' in text:
        text = text.split('## My request:', 1)[1]
    if '</environment_context>' in text:
        text = text.rsplit('</environment_context>', 1)[1]
    if text.lstrip().startswith(('<', 'Automation:', '# AGENTS.md')):
        return ''
    text = re.sub(r'<([A-Za-z_][\w-]*)\b[^>]*>.*?</\1>', '', text, flags=re.S)
    text = re.sub(r':codex-[a-z-]+(?:\[[^]]*\])?\{[^}]*\}', '', text)
    text = re.sub(r'\[([^]]+)\]\([^)]+\)', r'\1', text)
    text = text.replace('**', '').replace('`', '')
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    lines = [line for line in lines if not line.startswith(NOISE)]
    if not lines or text.lstrip().startswith(('# AGENTS.md', '<INSTRUCTIONS>', '<environment_context>', '<external_')):
        return ''
    return re.sub(r'\s+', ' ', ' '.join(lines))[:360]


def category(text):
    for name, pattern in [('research', r'论文|实验|研究|paper|research|benchmark'),
                          ('engineering', r'代码|实现|修复|部署|bug|python|code|cuda|git'),
                          ('learning', r'学习|解释|原理|课程|learn|explain')]:
        if re.search(pattern, text, re.I):
            return name
    return 'general'


def parse_session(path, provider):
    sid = path.stem
    candidates, seen = [], set()
    with path.open('rb') as f:
        for line_number, raw in enumerate(f, 1):
            try:
                d = json.loads(raw)
            except (ValueError, UnicodeError):
                continue
            if not isinstance(d, dict):
                continue
            if d.get('type') == 'session_meta':
                p = d.get('payload', {})
                if not isinstance(p, dict):
                    continue
                source = p.get('source', '')
                if isinstance(source, dict) and 'subagent' in source:
                    return sid, []
                sid = p.get('id', p.get('session_id', sid))
            elif provider == 'claude':
                sid = d.get('sessionId', sid)
            role, text = message(d, provider)
            quote = excerpt(text)
            if not quote or quote in seen:
                continue
            seen.add(quote)
            stamp = d.get('timestamp', '')
            if not isinstance(stamp, str):
                continue
            try:
                date = datetime.fromisoformat(stamp.replace('Z', '+00:00')).astimezone(timezone.utc).date().isoformat()
            except (ValueError, TypeError):
                continue  # Never substitute an invented conversation date.
            kind = 'request' if role == 'user' else 'reported_result'
            if re.search(r'未解决|待解决|还没|尚未|未完成|还需|unresolved|still broken|todo', quote, re.I):
                kind = 'open_question'
            elif role == 'user' and re.search(r'决定|确定采用|就用|选择采用|decided|let.s use', quote, re.I):
                kind = 'decision'
            eid = hashlib.sha256((provider + ':' + str(sid) + ':' + quote).encode()).hexdigest()[:24]
            candidates.append(dict(event_id=eid, date=date, title=quote[:64], summary=quote,
                                   category=category(quote), kind=kind, source_session_id=str(sid),
                                   source_provider=provider, source_path=str(path.resolve()),
                                   source_line=line_number, source_hash=hashlib.sha256(raw).hexdigest(),
                                   confidence=1.0))  # Evidence linkage, not a probability that a claim is true.
    # Keep the first request, last reported outcome, and latest explicit decision/question.
    selected = []
    for kind in ['request', 'reported_result', 'decision', 'open_question']:
        matches = [c for c in candidates if c['kind'] == kind]
        if matches:
            selected.append(matches[0] if kind == 'request' else matches[-1])
    return sid, selected


def import_history(store, root, provider, limit=100, max_bytes=16 * 1024 ** 2):
    root = Path(root).expanduser().resolve()
    if not root.is_dir():
        raise ValueError('History root is not a directory')
    if provider not in {'claude', 'codex'}:
        raise ValueError('Unsupported history provider')
    if not store.get('history_enabled', False):
        raise ValueError('History analysis is disabled. Enable it explicitly first.')
    started = time.perf_counter()
    paths = [p for p in root.rglob('*.jsonl') if not p.is_symlink() and p.stat().st_size <= max_bytes
             and root in p.resolve().parents]
    paths.sort(key=lambda p: p.stat().st_mtime_ns, reverse=True)
    report = dict(provider=provider, scanned=0, imported=0, cached=0, events=0, bytes=0, skipped_empty=0)
    for path in paths:
        if report['imported'] + report['cached'] >= limit:
            break
        report['scanned'] += 1
        stat = path.stat()
        with store.connect() as db:
            cached = db.execute('SELECT * FROM imports WHERE path=?', (str(path),)).fetchone()
        if (cached and cached['provider'] == provider and cached['extractor_version'] == EXTRACTOR_VERSION
                and cached['size'] == stat.st_size and cached['mtime'] == stat.st_mtime_ns):
            if cached['events']:
                report['cached'] += 1
                report['events'] += cached['events']
            continue
        sid, events = parse_session(path, provider)
        report['bytes'] += stat.st_size
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            enabled = db.execute('SELECT value FROM settings WHERE key="history_enabled"').fetchone()
            if not enabled or json.loads(enabled[0]) is not True:
                break
            reads = {r['event_id']: r['read_at'] for r in db.execute('SELECT event_id,read_at FROM timeline WHERE source_path=?', (str(path),))}
            db.execute('DELETE FROM timeline WHERE source_path=?', (str(path),))
            for event in events:
                keys = list(event) + ['read_at']
                db.execute('INSERT OR REPLACE INTO timeline (' + ','.join(keys) + ') VALUES (' + ','.join('?' for _ in keys) + ')',
                           list(event.values()) + [reads.get(event['event_id'], 0)])
            db.execute('INSERT OR REPLACE INTO imports VALUES (?,?,?,?,?,?,?)',
                       (str(path), provider, stat.st_size, stat.st_mtime_ns, str(sid), len(events), EXTRACTOR_VERSION))
        if events:
            report['imported'] += 1
            report['events'] += len(events)
        else:
            report['skipped_empty'] += 1
    report['seconds'] = round(time.perf_counter() - started, 3)
    return report


def select_content(store, mode='timeline', month='', topic='', limit=100):
    if not store.get('history_enabled', False):
        return []
    clauses, args = [], []
    if month:
        clauses.append('date LIKE ?')
        args.append(month + '%')
    if topic:
        clauses.append('category=?')
        args.append(topic)
    if mode == 'discovery':
        clauses.append("kind='open_question'")
    where = ' WHERE ' + ' AND '.join(clauses) if clauses else ''
    with store.connect() as db:
        rows = db.execute('SELECT * FROM timeline' + where + ' ORDER BY date DESC,(read_at=0) DESC LIMIT ?',
                          args + [min(limit, 200)]).fetchall()
    return [dict(row) for row in rows]


def markdown_excerpt(text):
    if not excerpt(text):
        return ''
    if '## My request:' in text:
        text = text.split('## My request:', 1)[1]
    if '</environment_context>' in text:
        text = text.rsplit('</environment_context>', 1)[1]
    text = re.sub(r'<(INSTRUCTIONS|environment_context|permissions|external_[\w-]*|system|developer)\b[^>]*>.*?</\1>', '', text, flags=re.S | re.I)
    text = re.sub(r':codex-[a-z-]+(?:\[[^]]*\])?\{[^}]*\}', '', text)
    lines = [line.rstrip() for line in text.splitlines() if not line.lstrip().startswith(NOISE)]
    return '\n'.join(lines).strip()[:1200]


@contextmanager
def source_stream(path):
    if path.is_file():
        with path.open('rb') as stream:
            yield stream, str(path)
        return
    compressed = Path(str(path) + '.zst')
    decoder = shutil.which('zstd') if compressed.is_file() else None
    if not decoder:
        raise FileNotFoundError('Original source is unavailable')
    # Read an adjacent compressed original only; never create an unpacked copy or use a shell.
    with subprocess.Popen([decoder, '-d', '-c', '-q', '--', str(compressed)], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as child:
        try:
            yield child.stdout, str(compressed)
        finally:
            child.stdout.close()
            if child.poll() is None:
                child.terminate()


def inspect_evidence(event):
    try:
        with source_stream(Path(event['source_path'])) as (f, resolved):
            consumed = 0
            for line in range(1, event['source_line'] + 1):
                raw = f.readline(16 * 1024 ** 2 - consumed + 1)
                consumed += len(raw)
                if not raw or consumed > 16 * 1024 ** 2:
                    break
                if line == event['source_line']:
                    if hashlib.sha256(raw).hexdigest() != event['source_hash']:
                        break
                    role, text = message(json.loads(raw), event['source_provider'])
                    if role and excerpt(text) == event['summary']:
                        result = dict(verified=True, markdown=markdown_excerpt(text))
                        if resolved != event['source_path']:
                            result['source_resolved_path'] = resolved
                        return result
                    break
    except (OSError, ValueError, TypeError):
        pass
    return dict(verified=False, markdown='')


def verify_evidence(event):
    return inspect_evidence(event)['verified']
