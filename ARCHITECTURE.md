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
                                                   └─ non-modal opt-in invitation
Explicit local import ─ Parser / extractor ─ Timeline ─ filtered cards
                                             └─ exact record hash + line reference
```

## Components

| Component | Ownership |
|---|---|
| `demo/app.py` | Start/stop/open/import/status/synthetic smoke CLI |
| `demo/hooks/` | Passive Claude plugin contract; no policy decisions |
| `core/state_manager.py` | Transactional per-provider/session turn state; invitation eligibility |
| `core/codex_watcher.py` | Read-only bounded JSONL tail; explicit experimental compatibility |
| `core/history_parser.py` | Parse, exclude instructions/secret patterns, extract, deduplicate, filter, verify |
| `core/chronicles.py` | Read-only topic classification, deduplicated inventory, sourced chapters and full chronology |
| `core/bottles.py` | Opt-in local shared pool, same-field policy, private per-instance identity, author retraction and replay receipts |
| `core/store.py` | Private SQLite schema, settings, derived-history deletion |
| `demo/server.py` | Loopback API, authentication, safe static allowlist, passive observer worker |
| `demo/ui/web/` | Framework-free accessible tabs, filters, evidence dialog, controls |
| `experiments/` | Synthetic regression / private evidence audit utilities |

Paths in this table are repository-relative for documentation only.

The intro's bottle panel is independent from the reading panel. Each companion
keeps its own random bottle identity in its private settings and uses a separate
same-machine pool, never the history tables. The existing authenticated API
exposes only explicit bottle operations; it never accepts a caller-supplied owner
or sends conversation material. SQL projections omit peer identities. Field
membership is rechecked on each read/write; SQLite write transactions serialize
cross-instance changes and cascading retractions. Non-content consumption hashes
prevent stale requests from resurrecting withdrawn posts/replies. See
[BOTTLES.md](BOTTLES.md) for the local-only contract and production exclusions.

`markdown.js` configures the vendored markdown-it browser bundle with raw HTML
disabled, no image fetches, and an explicit link-scheme allowlist. Only this
renderer produces history-related HTML. Existing normalized excerpts are not
modified: `/api/source` additionally returns a bounded, layout-preserving
Markdown excerpt after validating the same source line/hash and saved summary.
If only an adjacent `.jsonl.zst` file remains, an optional installed `zstd`
decoder streams its bytes into the identical checks, with a 16 MiB scan bound.
No shell, unpacked copy, guessed Markdown boundaries or source-data write is used.
An IntersectionObserver requests formatting for visible excerpts, deduplicates
requests in page memory, and ignores detached or history-disabled targets.
Source recovery is read-only and never marks a record read. The evidence dialog
still rechecks the source on each explicit open.

Live sessions sit in a collapsible list below the status strip, not a reading tab.
Only non-stale `WORKING` sessions enter the list/count. Each row has a native
button-styled jump link or an explicitly disabled unsupported-provider button;
completed and waiting-for-input signals remain stored but are not listed.
The UI creates only `codex://threads/<UUID>` navigation links for Codex sessions;
other providers remain status-only. Opening a chat uses the desktop URL handler,
not a new server-side shell endpoint or message/control channel. Session rows
are retained across tool/elapsed ticks so polling does not repeatedly replace
focused links. No conversation is automatically focused on lifecycle changes.

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

At five elapsed seconds of non-stale WORKING, `panel_due` makes a turn eligible
for an invitation, never an automatic open. The observer does not launch windows.
The reading section is always visible and loads on the first state response,
subject to the existing history consent gate. No enter/hide control remains.
Foreground reading suppresses invitations. In the background, the page aggregates
concurrent eligible turns into a non-modal invitation with entry/decline buttons;
entry scrolls to the existing reading section. Turn keys offered in this tab are
deduplicated across reloads in bounded session storage.
Disabling the legacy `auto_show` setting suppresses invitations across restarts.
The legacy `opened_turn` column remains for schema compatibility, but the old
transactional open-claim path is removed.

With explicit browser-notification permission, a live background page may send
a dismissible invitation; only its still-current click may focus the page.
No permission is requested automatically, no service worker/native notification
bridge is installed, and closed/frozen pages cannot guarantee delivery. Completion
does not focus or reopen anything. CLI `open` / `--open` is an explicit user action.

## Recovery and compatibility

Discovery's external search is separate from local history selection. Its local
catalog GET performs no network access. Only a consented search POST reaches the
fixed arXiv/Google News feed URLs, using public field queries and user keywords;
the adapter never receives a Store. Metadata is size/date/URL bounded, cached
only in memory, and rendered as text. A private cross-process arXiv timestamp
lock enforces one request/connection per three seconds across local profiles.
Provider redirects and arbitrary URL fetches are disabled. Source coverage and
explicit WeChat fallback limits are documented in [DISCOVERY.md](DISCOVERY.md).

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
