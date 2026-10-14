# Validation and evidence ledger — 2026-10-14

## Contract

This is a local CPU/browser prototype, not a GPU or retention benchmark. Freeze:
Python 3.9.6, macOS arm64 / Darwin 25.4.0, standard-library SQLite/HTTP, no model
API, explicit history consent, five-second panel threshold, per-session/turn
isolation, no focus change on completion, and no host permission decisions.
There is no loading-animation performance comparator or user-outcome baseline;
the observations below are resource measurements and correctness gates only.

Implementation, synthetic behavior, live host observation, semantic quality and
user value are separate gates. This record was assembled during the first local
implementation, not presented as a prospectively registered user experiment.

## Reproducible gates

```sh
python3 -m unittest discover -s tests -v
python3 -m compileall -q demo experiments tests
node --check demo/ui/web/app.js
python3 experiments/benchmark.py
python3 experiments/evaluate_history.py
```

All 23 unit tests passed. Python compilation and JavaScript syntax validation
passed separately. The unit suite covers delayed single-open behavior, permissions and synchronous
questions, recoverable tool errors, multiple sessions/providers, late/duplicate
turn events, stale uncertainty, abnormal SessionEnd, restart persistence,
consent, credential/context exclusion, source tampering, deduplication/read cache,
partial-line append and rotation, large-rollout start recovery, per-file extractor
versions/provider corrections, transactional open races, private file modes,
HTTP auth/Host/Origin/static boundaries, settings/deletion, and completion-feed
delivery across intervening turns without startup-replay notifications.

The synthetic benchmark has 30 scenarios, 180 state assertions and exactly one
open for each tested long turn. Source event times are virtual for delay tests;
CPU timings are wall time per SQLite state application. Raw ordered timings are
retained in the private `synthetic-benchmark.json`. These are **not 30 real host
tasks**, and no real-task >=95% accuracy claim is made.

## Claim-evidence ledger

| Claim | State | Evidence / denominator | Allowed wording |
|---|---|---|---|
| Lifecycle state/debounce implementation | partial | Unit regressions and 30 synthetic sequences / 180 assertions | Synthetic state contract passes; real accuracy unknown |
| Real historical data path | measured | 100 distinct real local sessions, 223 excerpts | Import and provenance work for this eligible subset |
| Exact source provenance | measured | Frozen random 50/50 record hashes and normalized excerpts match | Exact-source support, not human truth/semantic accuracy |
| Current host work can update UI | partial | Current real Codex turn observed in local rollout + browser status | Read-only local signal-to-UI chain observed |
| Completion without interruption | partial | Persisted feed regression plus labeled synthetic browser smoke | Synthetic behavior verified; live multi-task reliability pending |
| Claude host integration | unvalidated | Plugin contract and passive subprocess hook tests only | Packaged, not live-host accepted |
| User experience / return / retention improvement | unknown | No participants, control arm, or outcome data | Hypothesis only |

## Resource scope

On one ten-second connected-service sample, process RSS was approximately
20–22 MiB and CPU time increased by 0.12 seconds (about 1.2% of one core during
that interval; not a sustained-load guarantee). The process was also observing
live local rollouts, so this is not a pure idle measurement. The derived SQLite
store was approximately 0.72 MiB before subsequent test transitions. No GPU,
remote host, checkpoint, or shared process was touched.

One cold import (new temporary derived store) took 2.97 seconds process wall time,
2.898 seconds inside the importer, and peaked at 100.0 MiB RSS. It selected 100
sessions / 223 cards while considering eligible files totaling about 1.98 GB;
subagent files are skipped after metadata, so that is **not** measured bytes read
or a parsing-throughput denominator. Raw report/time output is retained privately.
API/UI polling is one second; the observer ticks at
0.5 seconds and discovers new rollout paths every five seconds. Actual host event
emission and browser throttling add latency; this is not a guaranteed reminder SLA.

## Browser QA

The real local store rendered 100 sessions / 223 excerpts. Timeline rendered its
100-card page; Discovery showed 42 historical unresolved/pending excerpts;
Progress showed isolated observed sessions. Source inspection displayed the
matching record-hash indicator. Manual close hid content; a new synthetic long
turn reopened it. After the synthetic turn ended, the completion notice appeared
while the evidence dialog stayed open, Timeline stayed selected, and focus
remained on the dialog's close button. This is a synthetic browser smoke test,
not a real Claude stop or 30-task host acceptance. Notification permission was
not granted automatically. Deletion was tested only against disposable fixtures.

## Negative evidence and fixes

| Observation | Decision / reopen condition |
|---|---|
| Initial fixed port occupied by an existing SSH listener | Preserved owner; changed default to OS-assigned port |
| Watcher first scan delayed because monotonic clock starts near zero | Initialize last-scan to negative infinity; regression runs without waiting |
| Source normalization changed while old server process was live | Restart service and reconnect after code changes; do not call stale-process output final QA |
| Truncated tail missed a long active turn | Recover prior lifecycle boundary; test >3 MiB tool output |
| Cache provider/version could wrongly reuse old results | Per-file version/provider validity and limited-upgrade tests |
| Panel claim snapshot raced with completion/new turn | Recheck exact turn, WORKING state and age inside transaction |
| Completion could occur between UI polls or be replayed at startup | Persistent transition cursor plus observation-start timestamp boundary |
| Go/tmux absent for Waiting Room | Cloned/reviewed but not run; no claim of runtime parity |
| GitHub repository did not exist; browser creation route timed out | Local checkpoint only; create an authenticated matching remote before push |

## Remaining acceptance work

1. Live Claude test with trusted plugin and a genuine long turn, including
   permission prompt, normal stop, recoverable tool error and abort.
2. >=30 independently labeled real tasks, >=95% transition accuracy, no repeated
   popup from tool activity, and observed completion reminder/focus behavior.
3. Fifty-event human semantic audit at >=90% supported key facts.
4. Browser/OS notification behavior with background, frozen and closed pages.
5. Only then admit the user study; no retention, business or novelty conclusion
   follows from the current prototype.
