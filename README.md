# Between — Agent Waiting Experience

A local waiting panel with an evidence-linked conversation timeline. No model
API, third-party Python package, telemetry, or host source modification is needed.
The interface is in Chinese; project documentation is in English.

**Implemented:** lifecycle state machine, five-second optional waiting invitation, Timeline /
Discovery, collapsible live sessions, non-interrupting completion notices, per-session isolation,
local import/deduplication, source-record verification, and privacy controls.
The intro also has an opt-in **research drift-bottle exchange** for two local
profiles: shared fields, same-field notes/replies, author-only retraction and no
automatic history sharing. This pilot is not publicly deployed.
**Not yet accepted:** 30 real host-task accuracy trials, a human semantic audit of
50 events, live Claude Code execution, and the user study. Synthetic tests do not
replace these gates.

## Run on macOS / Linux

Python 3.9+ is sufficient. All commands below are run from this repository root.

```sh
# Explicit consent: import 100 eligible local Codex sessions. No content is sent out.
python3 demo/app.py import-history --provider codex --limit 100 --consent

# Start once; use a free loopback port, watch local lifecycle records, open the UI.
python3 demo/app.py start --watch-codex --open
```

On macOS, double-click `demo/start.command` after the consented import. It starts
the same service and opens the panel. It does not install a login item. Once the
service and browser page are running, subsequent observed turns need no per-task
UI command. Starting without `--open` observes quietly and never launches a
browser in response to a task. Opening the page is not consent to enter its
reading panel: use **进入等待空间** when you want to read.

```sh
python3 demo/app.py open       # Reopen, or reconnect after a service restart
python3 demo/app.py status     # Inspect local state (may contain private session IDs)
python3 demo/app.py stop       # Authenticated shutdown; never kill by process name
python3 demo/app.py delete-history
```

`start` is detached; logs and access key are kept in the private data directory.
Use `serve` instead for foreground development. `--port N` pins an explicit port;
the default `0` avoids interfering with existing services. A port conflict fails
without terminating its owner. `--data-dir PATH` before the subcommand or
`AWE_DATA_DIR` overrides the private store. Windows is not supported by this MVP's
Unix process lock / launcher.

### Claude Code integration

The `demo` directory is a standard local plugin with `hooks/hooks.json`. Start the
service, then load it through the host's normal plugin flow:

```sh
python3 demo/app.py start --open
claude --plugin-dir "$PWD/demo"
# Optional, separate history consent:
python3 demo/app.py import-history --provider claude --limit 100 --consent
```

Review and trust the plugin in the host when requested. No settings or trust
records are edited automatically. Hooks only observe; they emit no model
instructions or permission decisions. The service and browser page must be
running for waiting invitations. The current machine has no `claude` executable, so this packaging has
only fixture/subprocess validation, not live-host acceptance. See the
[official hook contract](https://code.claude.com/docs/en/hooks).

### Codex compatibility boundary

The status strip opens a collapsible session list, separate from the reading
panel. Active and waiting sessions come first; recent observed sessions remain
available below. Project names precede lifecycle states. For
Codex this prefers the matching title in the local `session_index.jsonl` beside
the rollout directory, falling back to the session's working-directory basename.
Claude Hooks use the working-directory basename. Unknown names are labeled
explicitly; no full working-directory path is added to state storage or display.

Click a supported local Codex session to open its matching chat in the installed
ChatGPT desktop app. The link uses the documented
[`codex://threads/<thread-id>` scheme](https://learn.chatgpt.com/docs/reference/commands#deep-links)
and accepts only UUID-shaped Codex IDs. It only navigates: no prompt, approval,
resume command, or model API is sent. Other providers or unsupported IDs show
status only. The desktop app and its URL handler must be installed; browser/OS
confirmation may be required. This does not add cloud-chat or remote-host
discovery. The observer's latest 100 stored sessions are shown; collapsing this
list does not collapse the reading panel, and vice versa.

`--watch-codex` is an **experimental read-only rollout adapter**, not an installed
Codex hook or stable public API. It observes explicit local `task_started`,
`task_complete`, and `turn_aborted` events. Tool activity does not reset the turn
timer. It does not grant permissions, send prompts, read reasoning for display,
or change any Codex configuration. Permission dialogs are not reliably observable
through rollout files; supported synchronous question tools are recognized, but
this is not permission-state parity with Claude Hooks.

Official Codex lifecycle hooks require review/trust, as documented in
[plugin packaging](https://developers.openai.com/plugins/build/plugins). This
MVP does not manipulate that trust state or claim to install such hooks.

## Research drift bottles

The intro has a small bottle icon and pale **投递 / 收回** buttons. Only clicking
**投递** reveals field selection; **收回** opens your bottles and replies, with
same-field picking in a secondary tab. Choosing fields does not submit them;
explicit consent and the continue button are required. Bottles and replies have
separate consent checks. The matching-field pool is genuinely shared by separate
local companion profiles, but is empty until somebody explicitly posts. No fake
users or seeded personal stories are supplied. The usual reading panel remains
available without joining. See [BOTTLES.md](BOTTLES.md) for the two-profile launch,
privacy/retraction semantics and the intentionally local-only acceptance boundary.

## What the timeline means

- Timeline opens a thematic shelf: research/experiments, embodied/sensing,
  tools/creation, life/choices, and unassigned fragments. Open a volume to see its
  sourced request, explicit choice (when present), self-reported result,
  historical unresolved question, and all stored records ordered by date.
  Within one day, records follow session and source-line order; cross-session
  ordering is unknown. Chapters are selected excerpts, not verified milestones.
- Classification is local keyword matching, not a model-generated biography.
  Cross-topic records may appear in several volumes; the global event/session
  inventory remains deduplicated. Unmatched records stay visible instead of being
  forced into an unsupported story. The month filter scopes both counts and text.
- A volume reads every matching stored excerpt, not the old 100-card timeline
  page. Kind filters distinguish requests, choices, reported results and historical
  questions. Chapters with no supporting record are omitted, never invented.
- Cards are bounded excerpts of user text / final assistant messages, not invented
  biographical facts. No analysis or tool-output record is displayed.
- Chapters, cards and the evidence dialog render Markdown headings, lists,
  emphasis, tables, quotes and fenced code. The legacy 360-character normalized
  excerpt, IDs and evidence hashes remain unchanged. Visible excerpts lazily
  recover up to 1,200 characters of original Markdown from the same source record
  only after its hash and saved excerpt match. Missing/changed sources fall back
  to the stored excerpt; lost list/table boundaries are never guessed. An
  adjacent `.jsonl.zst` original can be read through an installed `zstd` CLI;
  decompressed lines must pass the identical hash/excerpt checks. No unpacked
  file is created, and the source dialog shows the compressed source path.
  Without the original/decoder, the view explicitly labels the saved fallback.
- Shelf previews and card titles show readable text rather than Markdown tokens.
  Formatting requests do not mark records read, reimport history or mutate the DB.
- An assistant-reported result is not independent proof of task completion.
- Discovery finds explicit historical unresolved/pending wording; it does not
  assert that the issue remains open today.
- Each card has a session ID, source file, line number, and SHA-256 of that source
  record. “View source” checks the record and normalized excerpt again.
- Confidence `1.0` means extractive evidence linkage, not semantic truth.
- Dates use the source UTC date. Topic/kind detection is heuristic. Results are
  deduplicated per session/excerpt; unchanged files are cached; changed files are
  rebuilt while preserving stable cards' read markers.
- Initial imports select the newest eligible non-subagent sessions with usable
  excerpts and files at most 16 MiB. This deliberately excludes large transcripts;
  “100 imported” never means a complete archive was analyzed.

See [TIMELINE_EVALUATION.md](TIMELINE_EVALUATION.md) for the measured scope and
[EVENT_EXTRACTION.md](EVENT_EXTRACTION.md) for extraction rules / a future prompt.

## Privacy and control

Default storage: `~/.local/share/agent-waiting-experience/`, directory `0700`,
SQLite/access-key/log files `0600`. The server binds only to `127.0.0.1`.
Private API routes require a random bearer key; cross-origin requests and invalid
Host headers are rejected. There is no CORS, remote font, external asset, model
request, or analytics endpoint. Metadata uses DOM `textContent`; Markdown uses
the locally bundled markdown-it parser with raw HTML disabled. Remote images are
rendered as labels, not loaded. Links allow only HTTP(S) without credentials and
strict local chat deep links; web links use `noopener noreferrer`. No CDN or
runtime package download is needed. See the vendored license and integrity
manifest in `demo/ui/web/vendor/README.md`. Formatting caches stay in page memory
and are cleared when history is disabled; disconnected/disabled views ignore
in-flight formatting responses.
The bootstrap key is a URL fragment, not an HTTP query or server access log.

Opt-in bottles use a separate private same-machine database, not the conversation
timeline. Only selected fields and manually consented editor text enter that
pool; no HTTP upload leaves the machine. Peer identities are not displayed, but
the OS account/operator can inspect the unencrypted pool. Retracting content
preserves only request-consumption hashes to prevent delayed replay. History
deletion and bottle withdrawal are separate controls; neither recalls screenshots,
already delivered pages or backups. Do not expose either loopback instance.

History import requires `--consent` for a selected root. The UI can disable
history display/analysis without deleting the originals. Deletion removes the
derived timeline, import cache, and generated human-review CSV, and disables
analysis. No background reimport exists. Filesystem snapshots, backups, user-made
exports, and the original sessions are not secure-erased. The store is not
encrypted; the same OS user can read it. Credential-pattern exclusion is
best-effort, not a guarantee that all sensitive prose is detected. Keep it off
shared screens and never publish the private data directory.

Waiting never launches a browser, expands the reading panel, or steals focus.
The panel starts collapsed. After five seconds of observed work, a non-modal
corner invitation offers **进入等待空间** / **暂不进入**. Only an explicit entry
click expands the content. Declining or closing suppresses invitations for the
observed turns; the tab remembers offers across reloads (bounded to 200 turn keys
in session storage). Concurrent turns share one invitation. Finished, stale or
waiting-for-input turns no longer invite. Disable **等待邀请** to suppress future
invitations; the existing `auto_show` setting is retained for compatibility, but
now controls invitations, never automatic opens. The legacy `opened_turn` DB
column is preserved without further use; existing evidence is not migrated.

Completion produces an in-page notice without changing the selected mode, scroll
position, or focus. Optional browser notifications need the user's permission
and a live browser page. Background waiting notifications are dismissible; only
clicking a still-current invitation focuses the page and enters. Closing the
browser page means no invitation delivery; frozen pages and OS/browser restrictions
can also delay or block delivery. No notification permission is requested
automatically. An explicit CLI `open` / `--open` remains user-initiated. There is
no percentage-progress estimate or native always-on-top window.

## Reproduce validation

```sh
python3 -m unittest discover -s tests -v
python3 -m compileall -q demo experiments tests
node --check demo/ui/web/app.js   # Optional Node.js syntax check
node --test tests/test_ui.cjs     # Optional Node.js UI and session-link regressions
python3 experiments/benchmark.py # 30 SYNTHETIC scenarios, not 30 real tasks
python3 experiments/evaluate_history.py
python3 demo/app.py simulate --seconds 8  # Clearly labeled synthetic UI smoke test
```

Generated evidence and review excerpts remain outside Git, in the private data
directory. See [FEASIBILITY.md](FEASIBILITY.md), [ARCHITECTURE.md](ARCHITECTURE.md),
[VALIDATION.md](VALIDATION.md), and [USER_STUDY.md](USER_STUDY.md). Prototype / local
pilot only; no retention or user-value claim is established.
