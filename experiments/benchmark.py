#!/usr/bin/env python3
"""Synthetic state-machine regression; never count these as real host tasks."""
import json
import statistics
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'demo'))
from core.state_manager import StateManager
from core.store import Store


def main():
    checks = passed = opens = 0
    timings = []
    with tempfile.TemporaryDirectory() as root:
        manager = StateManager(Store(root))
        for i in range(30):
            session = 'synthetic-' + str(i)
            sequence = [('UserPromptSubmit', 'WORKING', ''), ('PreToolUse', 'WORKING', 'Bash'),
                        ('PermissionRequest', 'WAITING_USER', ''), ('PostToolUse', 'WORKING', 'Bash'),
                        ('PostToolUseFailure', 'WORKING', 'Bash'), ('Stop', 'COMPLETED', '')]
            for j, (event, expected, tool) in enumerate(sequence):
                started = time.perf_counter()
                manager.apply(session, 'demo', event, now=100 + j, tool=tool)
                timings.append((time.perf_counter() - started) * 1000)
                actual = next(r for r in manager.snapshot(105) if r['id'] == 'demo:' + session)
                checks += 1
                passed += actual['state'] == expected
            manager.apply(session, 'demo', 'UserPromptSubmit', now=110)
            opens += manager.claim_open(115)
            assert not manager.claim_open(116)
            manager.apply(session, 'demo', 'Stop', now=117)
    report = dict(label='SYNTHETIC_NOT_REAL_HOST_ACCEPTANCE', scenarios=30, checks=checks,
                          passed=passed, single_open_turns=opens,
                          apply_ms_median=round(statistics.median(timings), 3),
                          apply_ms_p95=round(sorted(timings)[int(len(timings) * .95)], 3))
    output = Store().root / 'synthetic-benchmark.json'
    output.write_text(json.dumps(dict(report, apply_ms_order=timings), indent=2))
    print(json.dumps(report, indent=2))
    assert checks == passed and opens == 30


if __name__ == '__main__':
    main()
