# Architecture

## Boundary

This is a standalone local companion, not an injected host sidebar. Claude Hooks
or the opt-in Codex rollout reader feed a SQLite state manager. The same local
HTTP server serves static UI and authenticated JSON APIs. Only the explicit CLI
importer reads conversation content; the lifecycle observer stores session/turn
IDs, event names, safe tool names, state, and timestamps, not prompt/tool bodies.

```text
Claude lifecycle.py ────────┐
                            ├─ StateManager ─ SQLite ─ Server ─ Browser panel
Opt-in Codex rollout tail ─┘                        │
                                                   └─ delayed browser opener
Explicit local import ─ Parser / extractor ─ Timeline ─ filtered cards
                                             └─ exact record hash + line reference
```

## Components

| Component | Ownership |
|---|---|
| `demo/app.py` | Start/stop/open/import/status/synthetic smoke CLI |
| `demo/hooks/` | Passive Claude plugin contract; no policy decisions |
| `core/state_manager.py` | Transactional per-provider/session turn state; panel debounce |
| `core/codex_watcher.py` | Read-only bounded JSONL tail; explicit experimental compatibility |
| `core/history_parser.py` | Parse, exclude instructions/secret patterns, extract, deduplicate, filter, verify |
| `core/chronicles.py` | Read-only topic classification, deduplicated inventory, sourced chapters and full chronology |
| `core/store.py` | Private SQLite schema, settings, derived-history deletion |
| `demo/server.py` | Loopback API, authentication, safe static allowlist, opener worker |
| `demo/ui/web/` | Framework-free accessible tabs, filters, evidence dialog, controls |
| `experiments/` | Synthetic regression / private evidence audit utilities |

Paths in this table are repository-relative for documentation only.

The authenticated `/api/chronicles` route groups already-consented stored excerpts
without reimporting histories, mutating evidence, or using a model API. Topics are
keyword matches with research/general fallbacks. Cross-references are explicit;
inventory counts unique original records, not summed topic memberships. Dossier
chapters select existing records by date/kind and preserve their exact source
references. Dates have day precision: same-day records follow session and
source-line order, not an inferred cross-session timestamp. No record means no
chapter, not an inferred decision or achievement.

## State contract

| Signal | State / behavior |
|---|---|
| SessionStart | IDLE unless an active persisted state already exists |
| UserPromptSubmit / task_started | New WORKING turn; timer starts once |
| ordinary Pre/PostToolUse | WORKING; no timer reset or repeated popup |
| AskUserQuestion / synchronous request_user_input | WAITING_USER |
| PermissionRequest / permission_prompt notification | WAITING_USER; never approve |
| tool result / subsequent tool execution | Resume WORKING |
| PostToolUseFailure | Remain WORKING; a recoverable tool error is not turn failure |
| Stop / task_complete | COMPLETED means the **turn ended**, not that its result is correct |
| StopFailure / turn_aborted | FAILED / interrupted |
| SessionEnd during active work | FAILED, with unconfirmed-completion explanation |
| >15 minutes without a signal | Mark stale/uncertain; do not infer failure or reopen |

Keys include provider + session ID. Turn IDs and monotonic source byte offsets
reject stale/duplicate rollout events. Claude payloads without turn IDs cannot
fully disambiguate late out-of-order old-turn hooks: command hooks are kept
synchronous and bounded to reduce this risk, not claimed to eliminate it.
SQLite writes are short transactions with a timeout. No schema is written to a
host-owned database. A Unix lock prevents duplicate services on one data store.

At five elapsed seconds of WORKING, the service claims one open per turn. An
already-connected page updates without another browser launch; otherwise it
requests an OS browser open, at most once per ten seconds globally. A false or
blocked OS browser launch is not proof that a panel was actually seen. Closing
content suppresses it for the page's known turns; disabling auto-show persists
across service restarts. No window is focused on completion.

## Recovery and compatibility

The DB survives service restart. The rollout reader recovers the last lifecycle
boundary before a 2 MiB tail for files modified within 24 hours, then processes at most 10,000 complete
records per file/tick. It retains partial final JSONL lines until completed and
detects truncation / inode replacement. Replayed byte offsets do not reopen a
completed turn. Startup can scan backward through large output records to recover
the preceding lifecycle boundary; this is not a constant-time guarantee. Missing
lifecycle records remain unknown; stale events are not proof of an idle host. An abnormal host exit
without a lifecycle record cannot be identified reliably by this adapter.

No automatic logon service is installed. After reboot the user restarts the
companion. A restart rotates the access key; `app.py open` reconnects the panel.
Do not use this MVP as a safety-critical completion or permission monitor.
