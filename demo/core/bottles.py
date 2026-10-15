"""Opt-in, same-machine peer exchange, isolated from conversation history."""
import os
import json
import hashlib
import re
import secrets
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path


FIELDS = {
    'ml': '机器学习', 'gpu': 'GPU 与体系结构', 'database': '数据库与检索',
    'graph': '图学习与时序图', 'robotics': '具身智能与机器人', 'vision': '计算机视觉',
    'nlp': '自然语言处理', 'math': '数学与统计', 'bio': '生命科学',
    'physics': '物理与材料', 'social': '社会科学', 'other': '跨学科与其他',
}
UUID = re.compile(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}')


class BottleError(Exception):
    def __init__(self, status, message):
        self.status = status
        super().__init__(message)


class BottleBoard:
    def __init__(self, store, root=None):
        self.store = store
        self.root = Path(root or os.environ.get('AWE_BOTTLE_DIR',
                         Path.home() / '.local/share/agent-waiting-bottles'))
        self.path = self.root / 'bottles.db'
        self.lock = threading.Lock()

    @contextmanager
    def connect(self):
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.root.is_symlink() or self.root.stat().st_mode & 0o077:
            raise BottleError(503, '漂流瓶数据目录必须是独立的私有目录。')
        if self.path.is_symlink():
            raise BottleError(503, '漂流瓶数据库不能是符号链接。')
        fd = os.open(str(self.path), os.O_CREAT | os.O_RDWR, 0o600)
        os.close(fd)
        if self.path.stat().st_mode & 0o077:
            raise BottleError(503, '漂流瓶数据库权限必须为 0600。')
        db = sqlite3.connect(str(self.path), timeout=5)
        db.row_factory = sqlite3.Row
        try:
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('PRAGMA secure_delete=ON')
            schema = '''
                CREATE TABLE IF NOT EXISTS members (
                    owner TEXT PRIMARY KEY, interests TEXT NOT NULL, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS bottles (
                    id TEXT PRIMARY KEY, owner TEXT NOT NULL REFERENCES members(owner) ON DELETE CASCADE,
                    field TEXT NOT NULL, body TEXT NOT NULL, created REAL NOT NULL, nonce TEXT NOT NULL,
                    UNIQUE(owner,nonce));
                CREATE INDEX IF NOT EXISTS bottle_field ON bottles(field,created);
                CREATE TABLE IF NOT EXISTS replies (
                    id TEXT PRIMARY KEY, bottle_id TEXT NOT NULL REFERENCES bottles(id) ON DELETE CASCADE,
                    owner TEXT NOT NULL REFERENCES members(owner) ON DELETE CASCADE,
                    body TEXT NOT NULL, created REAL NOT NULL, nonce TEXT NOT NULL, UNIQUE(owner,nonce));
                CREATE TABLE IF NOT EXISTS consumed_requests (digest TEXT PRIMARY KEY);
            '''
            # Schema, backfill and completion marker must be one writer transaction.
            db.execute('BEGIN IMMEDIATE')
            with db:
                receipts_exist = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='consumed_requests'").fetchone()
                migrated = db.execute('PRAGMA user_version').fetchone()[0] >= 1
                for statement in schema.split(';'):
                    if statement.strip():
                        db.execute(statement)
                if not receipts_exist or not migrated:
                    for table in ['bottles', 'replies']:
                        db.executemany('INSERT OR IGNORE INTO consumed_requests VALUES (?)',
                                       ((self.receipt(r['owner'], table, r['nonce']),) for r in db.execute('SELECT owner,nonce FROM ' + table)))
                    db.execute('PRAGMA user_version=1')
            with db:
                yield db
        finally:
            db.close()

    def profile(self, interests):
        return dict(joined=bool(interests), interests=interests,
                    fields=[dict(id=k, label=v) for k, v in FIELDS.items()], scope='local')

    def status(self):
        owner = self.store.get('bottle_owner')
        if not owner or not self.path.exists():
            return self.profile([])
        with self.lock, self.connect() as db:
            row = db.execute('SELECT interests FROM members WHERE owner=?', (owner,)).fetchone()
        return self.profile(json.loads(row['interests']) if row else [])

    @staticmethod
    def receipt(owner, table, nonce):
        return hashlib.sha256((owner + ':' + table + ':' + nonce).encode()).hexdigest()

    @staticmethod
    def text(value, limit):
        if not isinstance(value, str) or not 1 <= len(value.strip()) <= limit:
            raise BottleError(400, '请填写 1–' + str(limit) + ' 字的文字。')
        if any(ord(c) < 32 and c not in '\r\n\t' for c in value):
            raise BottleError(400, '文字含有不支持的控制字符。')
        return value.strip()

    @staticmethod
    def identifier(value):
        if not isinstance(value, str) or not UUID.fullmatch(value):
            raise BottleError(400, '无效的漂流瓶请求标识。')
        return value

    def visible(self, db, bottle_id, owner, interests):
        row = db.execute('SELECT * FROM bottles WHERE id=?', (self.identifier(bottle_id),)).fetchone()
        if not row or (row['owner'] != owner and row['field'] not in interests):
            raise BottleError(404, '这只瓶子已撤回，或不属于你共享的领域。')
        return row

    @staticmethod
    def view(db, row, owner):
        replies = [dict(id=r['id'], body=r['body'], created=r['created'], mine=r['owner'] == owner,
                        from_author=r['owner'] == row['owner']) for r in db.execute(
            'SELECT * FROM replies WHERE bottle_id=? ORDER BY created,id LIMIT 100', (row['id'],))]
        return dict(id=row['id'], field=row['field'], body=row['body'], created=row['created'],
                    mine=row['owner'] == owner, replies=replies)

    def command(self, action, body):
        keys = {
            'profile': {'interests', 'consent'}, 'withdraw': {'confirm'},
            'throw': {'field', 'body', 'consent', 'request_id'}, 'pick': {'field', 'exclude'},
            'read': {'bottle_id'}, 'mine': set(),
            'reply': {'bottle_id', 'body', 'consent', 'request_id'},
            'delete': {'bottle_id', 'confirm'}, 'delete-reply': {'reply_id', 'confirm'},
        }
        if action not in keys:
            raise BottleError(404, '没有这个漂流瓶操作。')
        if set(body) - keys[action]:
            raise BottleError(400, '请求包含未支持的字段。')
        with self.lock:
            owner = self.store.get('bottle_owner')
            if action == 'profile':
                interests = body.get('interests')
                if body.get('consent') is not True:
                    raise BottleError(400, '请先明确同意共享所选领域。')
                if not isinstance(interests, list) or not 1 <= len(interests) <= 5 or any(
                        not isinstance(f, str) or f not in FIELDS for f in interests):
                    raise BottleError(400, '请选择 1–5 个有效领域。')
                interests = list(dict.fromkeys(interests))
                if not owner:
                    owner = secrets.token_hex(32)
                    self.store.set('bottle_owner', owner)
            with self.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                if action == 'profile':
                    slots = ','.join('?' for _ in interests)
                    db.execute('INSERT INTO members VALUES (?,?,?) ON CONFLICT(owner) DO UPDATE SET interests=excluded.interests',
                               (owner, json.dumps(interests), time.time()))
                    # Removing a field also retracts this member's contributions in that field.
                    db.execute('DELETE FROM replies WHERE owner=? AND bottle_id IN (SELECT id FROM bottles WHERE field NOT IN (' + slots + '))', (owner, *interests))
                    db.execute('DELETE FROM bottles WHERE owner=? AND field NOT IN (' + slots + ')', (owner, *interests))
                    return self.profile(interests)
                member = db.execute('SELECT interests FROM members WHERE owner=?', (owner,)).fetchone()
                if not member:
                    raise BottleError(403, '请先自愿选择并共享感兴趣的领域。')
                interests = json.loads(member['interests'])
                if action == 'withdraw':
                    if body.get('confirm') != 'WITHDRAW':
                        raise BottleError(400, '退出并撤回需要明确确认。')
                    db.execute('DELETE FROM members WHERE owner=?', (owner,))
                    return self.profile([])
                if action in {'throw', 'pick'} and body.get('field') not in interests:
                    raise BottleError(403, '只能向已共享的领域投递或捞取。')
                if action == 'pick':
                    exclude = body.get('exclude', [])
                    if not isinstance(exclude, list) or len(exclude) > 100:
                        raise BottleError(400, '捞取记录过长。')
                    exclude = [self.identifier(x) for x in exclude]
                    slots = ','.join('?' for _ in exclude) or 'NULL'
                    row = db.execute('SELECT * FROM bottles WHERE field=? AND owner<>? ' +
                                     ('AND id NOT IN (' + slots + ') ' if exclude else '') +
                                     'ORDER BY RANDOM() LIMIT 1', (body['field'], owner, *exclude)).fetchone()
                    return dict(bottle=self.view(db, row, owner) if row else None)
                if action == 'mine':
                    rows = db.execute('''SELECT b.*,(SELECT COUNT(*) FROM replies WHERE bottle_id=b.id) AS reply_count
                        FROM bottles b WHERE owner=? ORDER BY created DESC,id LIMIT 50''', (owner,))
                    bottles = [dict(id=r['id'], field=r['field'], body=r['body'], created=r['created'],
                                    reply_count=r['reply_count']) for r in rows]
                    replies = db.execute('''SELECT r.id,r.bottle_id,r.body,r.created,b.field FROM replies r
                        JOIN bottles b ON b.id=r.bottle_id WHERE r.owner=? ORDER BY r.created DESC,r.id LIMIT 50''', (owner,))
                    return dict(bottles=bottles, replies=[dict(r) for r in replies])
                if action in {'read', 'reply', 'delete'}:
                    row = self.visible(db, body.get('bottle_id'), owner, interests)
                    if action == 'read':
                        return dict(bottle=self.view(db, row, owner))
                if action in {'delete', 'delete-reply'}:
                    if body.get('confirm') != 'DELETE':
                        raise BottleError(400, '撤回内容需要明确确认。')
                    table, key = ('bottles', 'bottle_id') if action == 'delete' else ('replies', 'reply_id')
                    changed = db.execute('DELETE FROM ' + table + ' WHERE id=? AND owner=?',
                                         (self.identifier(body.get(key)), owner)).rowcount
                    if not changed:
                        raise BottleError(404, '只能撤回自己的内容，或内容已被撤回。')
                    return dict(ok=True)
                if action in {'throw', 'reply'}:
                    if body.get('consent') is not True:
                        raise BottleError(400, '请先同意共享这段文字。')
                    text = self.text(body.get('body'), 2000 if action == 'throw' else 800)
                    nonce = self.identifier(body.get('request_id'))
                    table = 'bottles' if action == 'throw' else 'replies'
                    previous = db.execute('SELECT * FROM ' + table + ' WHERE owner=? AND nonce=?', (owner, nonce)).fetchone()
                    target = body['field'] if action == 'throw' else row['id']
                    if previous:
                        if previous['body'] != text or previous['field' if action == 'throw' else 'bottle_id'] != target:
                            raise BottleError(409, '请求标识已用于其他内容。')
                        bottle = previous if action == 'throw' else row
                        return dict(bottle=self.view(db, bottle, owner))
                    digest = self.receipt(owner, table, nonce)
                    if db.execute('SELECT 1 FROM consumed_requests WHERE digest=?', (digest,)).fetchone():
                        raise BottleError(410, '这次提交已经撤回，不能通过重试重新共享。请修改草稿后重新确认。')
                    limit = 20 if action == 'throw' else 50
                    count = db.execute('SELECT COUNT(*) FROM ' + table + ' WHERE owner=? AND created>?', (owner, time.time() - 86400)).fetchone()[0]
                    if count >= limit:
                        raise BottleError(429, '今天先休息一下吧，已达到本机试用的发言上限。')
                    if action == 'reply' and db.execute('SELECT COUNT(*) FROM replies WHERE bottle_id=?', (row['id'],)).fetchone()[0] >= 100:
                        raise BottleError(409, '这只瓶子已经收到了 100 条回声。')
                    entry_id = str(uuid.uuid4())
                    # Retain only a hash so late retries cannot resurrect retracted text.
                    db.execute('INSERT INTO consumed_requests VALUES (?)', (digest,))
                    if action == 'throw':
                        db.execute('INSERT INTO bottles VALUES (?,?,?,?,?,?)', (entry_id, owner, target, text, time.time(), nonce))
                        row = db.execute('SELECT * FROM bottles WHERE id=?', (entry_id,)).fetchone()
                    else:
                        db.execute('INSERT INTO replies VALUES (?,?,?,?,?,?)', (entry_id, target, owner, text, time.time(), nonce))
                    return dict(bottle=self.view(db, row, owner))
