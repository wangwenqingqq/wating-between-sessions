#!/usr/bin/env python3
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.state_manager import StateManager
from core.store import Store


def main():
    # Never emit instructions or permission decisions, and never block the host on failure.
    try:
        data = json.loads(sys.stdin.read(1024 * 1024))
        if not isinstance(data, dict) or data.get('agent_id'):
            return
        StateManager(Store()).apply(data.get('session_id'), 'claude', data.get('hook_event_name'),
                                    turn_id=data.get('turn_id'), tool=data.get('tool_name', ''),
                                    notification=data.get('notification_type', ''),
                                    project_name=Path(data['cwd']).name if isinstance(data.get('cwd'), str) else None)
    except Exception:
        print('Waiting panel observer unavailable; host execution is unchanged.', file=sys.stderr)


if __name__ == '__main__':
    main()
