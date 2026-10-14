#!/usr/bin/env python3
"""Audit stored excerpts against original records; semantic human review is separate."""
import argparse
import csv
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'demo'))
from core.history_parser import verify_evidence
from core.store import Store


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--data-dir', type=Path)
    args = p.parse_args()
    store = Store(args.data_dir)
    with store.connect() as db:
        events = [dict(row) for row in db.execute('SELECT * FROM timeline ORDER BY event_id')]
    sample = random.Random(42).sample(events, min(50, len(events)))
    matches = sum(verify_evidence(e) for e in sample)
    audit = store.root / 'human-review.csv'
    with audit.open('w') as f:
        writer = csv.writer(f)
        writer.writerow(['event_id', 'kind', 'excerpt', 'source_path', 'line', 'human_supported', 'notes'])
        for e in sample:
            writer.writerow([e['event_id'], e['kind'], e['summary'], e['source_path'], e['source_line'], '', ''])
    print(json.dumps(dict(total_events=len(events), sample_size=len(sample), seed=42,
                          exact_evidence_matches=matches, human_semantic_review='PENDING',
                          audit_location='private data directory / human-review.csv'), indent=2))


if __name__ == '__main__':
    main()
