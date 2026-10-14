# Between — Agent Waiting Experience

A local waiting panel with an evidence-linked conversation timeline. No model
API, third-party Python package, telemetry, or host source modification is needed.
The interface is in Chinese; project documentation is in English.

**Implemented:** lifecycle state machine, five-second delayed display, Timeline /
Discovery / Progress, non-interrupting completion notices, per-session isolation,
local import/deduplication, source-record verification, and privacy controls.
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
service is running, subsequent observed turns need no per-task UI command.

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
instructions or permission decisions. The service must be running for automatic
display. The current machine has no `claude` executable, so this packaging has
only fixture/subprocess validation, not live-host acceptance. See the
[official hook contract](https://code.claude.com/docs/en/hooks).

### Codex compatibility boundary

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

## What the timeline means

- Cards are bounded excerpts of user text / final assistant messages, not invented
  biographical facts. No analysis or tool-output record is displayed.
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
request, or analytics endpoint. Text uses DOM `textContent`, never history HTML.
The bootstrap key is a URL fragment, not an HTTP query or server access log.

History import requires `--consent` for a selected root. The UI can disable
history display/analysis without deleting the originals. Deletion removes the
derived timeline, import cache, and generated human-review CSV, and disables
analysis. No background reimport exists. Filesystem snapshots, backups, user-made
exports, and the original sessions are not secure-erased. The store is not
encrypted; the same OS user can read it. Credential-pattern exclusion is
best-effort, not a guarantee that all sensitive prose is detected. Keep it off
shared screens and never publish the private data directory.

Close hides content for the current observed turns. Disable auto-show to suppress
future automatic opens. Completion produces an in-page notice without changing
the selected mode, scroll position, or focus. Optional browser notifications need
the user's permission and a live browser page; delivery is not guaranteed with a
closed/frozen browser or OS restrictions. No notification permission is granted
automatically. There is no percentage-progress estimate.

## Reproduce validation

```sh
python3 -m unittest discover -s tests -v
python3 -m compileall -q demo experiments tests
node --check demo/ui/web/app.js   # Optional Node.js syntax check
python3 experiments/benchmark.py # 30 SYNTHETIC scenarios, not 30 real tasks
python3 experiments/evaluate_history.py
python3 demo/app.py simulate --seconds 8  # Clearly labeled synthetic UI smoke test
```

Generated evidence and review excerpts remain outside Git, in the private data
directory. See [FEASIBILITY.md](FEASIBILITY.md), [ARCHITECTURE.md](ARCHITECTURE.md),
[VALIDATION.md](VALIDATION.md), and [USER_STUDY.md](USER_STUDY.md). Prototype / local
pilot only; no retention or user-value claim is established.
