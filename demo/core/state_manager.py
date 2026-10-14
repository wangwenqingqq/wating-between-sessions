import time
import uuid


STATES = {'IDLE', 'WORKING', 'WAITING_USER', 'COMPLETED', 'FAILED'}


class StateManager:
    def __init__(self, store):
        self.store = store

    def apply(self, session, provider, event, *, turn_id=None, tool='', notification='',
              sequence=0, now=None):
        if not isinstance(session, str) or not 0 < len(session) <= 200:
            raise ValueError('Invalid session ID')
        if provider not in {'claude', 'codex', 'demo'}:
            raise ValueError('Invalid provider')
        now = time.time() if now is None else now
        sid = provider + ':' + session
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM sessions WHERE id=?', (sid,)).fetchone()
            old = dict(row) if row else dict(state='IDLE', turn_id='', started=now,
                                            opened_turn='', sequence=0)
            if sequence and sequence <= old['sequence']:
                return
            if event != 'UserPromptSubmit' and turn_id and old['turn_id'] and turn_id != old['turn_id']:
                return  # A late stop from an older turn must not end the current turn.
            state, detail = old['state'], event
            turn = old['turn_id']
            started = old['started']
            if event == 'UserPromptSubmit':
                if turn_id and turn == turn_id:
                    return
                turn = turn_id or uuid.uuid4().hex
                state, started = 'WORKING', now
            elif event == 'SessionStart':
                state = 'IDLE' if not row else state
            elif event == 'PermissionRequest' or (event == 'Notification' and notification == 'permission_prompt'):
                if state in {'WORKING', 'WAITING_USER'}:
                    state = 'WAITING_USER'
                    detail = 'Permission needed; the observer cannot approve it.'
            elif event == 'PreToolUse' and tool in {'AskUserQuestion', 'request_user_input'}:
                if state == 'WORKING':
                    state = 'WAITING_USER'
            elif event in {'PreToolUse', 'PostToolUse', 'PostToolUseFailure'}:
                if state in {'WORKING', 'WAITING_USER'}:
                    state = 'WORKING'
                detail = event + (': ' + tool[:80] if tool else '')
            elif event == 'Stop':
                if state in {'WORKING', 'WAITING_USER'}:
                    state = 'COMPLETED'
                    detail = 'Turn ended; task correctness is not verified.'
            elif event in {'StopFailure', 'Interrupt'}:
                if state in {'WORKING', 'WAITING_USER'}:
                    state = 'FAILED'
            elif event == 'SessionEnd' and state in {'WORKING', 'WAITING_USER'}:
                state, detail = 'FAILED', 'Session ended without a confirmed turn completion.'
            elif event == 'Heartbeat':
                detail = 'Activity observed'
            elif event != 'Notification':
                return
            seq = sequence or old['sequence']
            db.execute('''INSERT OR REPLACE INTO sessions
                (id,provider,state,turn_id,started,updated,event,detail,opened_turn,sequence)
                VALUES (?,?,?,?,?,?,?,?,?,?)''',
                       (sid, provider, state, turn, started, now, event, detail, old['opened_turn'], seq))
            if state != old['state'] or turn != old['turn_id']:
                db.execute('INSERT INTO transitions(session_id,turn_id,state,event,timestamp) VALUES (?,?,?,?,?)',
                           (sid, turn, state, event, now))

    def snapshot(self, now=None):
        now = time.time() if now is None else now
        with self.store.connect() as db:
            rows = db.execute('SELECT * FROM sessions ORDER BY updated DESC LIMIT 100').fetchall()
        result = []
        for row in rows:
            d = dict(row)
            d['elapsed'] = max(0, now - d['started'])
            d['stale'] = d['state'] in {'WORKING', 'WAITING_USER'} and now - d['updated'] > 900
            # Silence is not evidence of failure: model reasoning and tools can run for hours.
            d['panel_due'] = d['state'] == 'WORKING' and d['elapsed'] >= 5 and not d['stale']
            result.append(d)
        return result

    def claim_open(self, now=None):
        now = time.time() if now is None else now
        if not self.store.get('auto_show', True):
            return False
        for session in self.snapshot(now):
            if not session['panel_due'] or session['opened_turn'] == session['turn_id']:
                continue
            with self.store.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                changed = db.execute('''UPDATE sessions SET opened_turn=turn_id
                    WHERE id=? AND turn_id=? AND state='WORKING' AND started<=? AND updated>=?
                    AND opened_turn<>turn_id''',
                                     (session['id'], session['turn_id'], now - 5, now - 900)).rowcount
            if changed:
                return True
        return False
