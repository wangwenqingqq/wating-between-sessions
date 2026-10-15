# Feasibility — 2026-10-14

## Decision

**GO for a local engineering prototype / personal pilot. NOT YET GO for a
15–30-person user study or the plan's complete real-host acceptance claim.**
The state-to-panel chain works without modifying host source, and 100 real local
sessions can be converted to evidence-linked excerpts without a model API. Live
Claude installation and 30 labeled host tasks remain separate, unpassed gates.

## Reference review (frozen checkouts)

| Reference | Source revision | License / maintenance | Checked / decision |
|---|---|---|---|
| [CCO Arcade](https://github.com/egorfedorov/cco-arcade) | `5cdfd6bb0e2ac0ff3ab961a5f5880d2bf7751d2d` | MIT; latest checked commit 2026-07-04; version 0.1.2 | Cloned; reviewed collector/server/hooks; ran isolated Node server and received HTTP 200 `/state`; stopped only the spawned PID. Reuse lifecycle architecture, not game/city code. |
| [Claude Waiting Room](https://github.com/alifarooqi/claude-waiting-room) | `f941e79eeb80548129635b69c54270c05968c574` | MIT; latest checked commit 2026-09-03; self-described pre-alpha | Cloned; inspected Go daemon / plugin hook transport. `make build-daemon` failed because Go is absent; tmux is also absent. Not run; no implicit toolchain install. A focus-switching Go/tmux stack is unnecessary for this non-interrupting browser MVP. |
| [chat-history](https://github.com/mblode/agent-skills/tree/main/skills/chat-history) | `872bc83bdb6dd54a9ff456fbf1181beea6db7875` | MIT repository license; latest checked commit 2026-10-11 | Cloned; reviewed JSONL decoder and synthetic-message exclusion. It supports read-only retrieval across several hosts. Implemented a narrower independent excerpt parser; no third-party skill copied or installed. |

These projects already establish lifecycle-driven waiting activities. This work
does **not** claim novelty for agent status detection, notifications, games, or
side panels. The remaining product hypothesis is whether consented, evidence-linked
personal history improves waiting experience. No user-value evidence exists yet.

## Host and permission evidence

- Local host: macOS arm64, system Python 3.9.6, Node.js available.
- `claude` not found on PATH. One Claude transcript found; not enough for a
  Claude-only 100-session evaluation. No Claude account or installation altered.
- 1,377 Codex rollout files found at inventory time. The opted-in import uses a
  bounded eligible subset, not all files and not external storage.
- Official [Claude Hooks](https://code.claude.com/docs/en/hooks) distinguish turn
  stop, permission requests, and tool failures. The plugin observes those events
  without returning policy decisions. A tool failure alone is not a task failure.
- Official [Codex plugin documentation](https://developers.openai.com/plugins/build/plugins)
  requires explicit hook trust. No trust/configuration was edited. Local rollout
  tailing is explicitly experimental, not represented as that official API.
- An existing SSH listener occupied the initial fixed port; it was preserved.
  Dynamic loopback binding replaced the fixed default.

## First-round checklist

| Plan item | Evidence state |
|---|---|
| Clone/run CCO Arcade | Ran isolated server; no live Claude integration |
| Clone/run Claude Waiting Room | Cloned/reviewed; runtime blocked by missing Go/tmux |
| Inspect chat-history format/search | Reviewed source and source references; not installed |
| Hook start/stop/permission validation | Contract fixtures and subprocess tests pass; real Claude pending |
| 100 real historical sessions | Imported locally; subset and quality caveats in evaluation |
| Independent UI updates / three modes | Implemented and browser-checked |
| Delayed opt-in invitation | Replaces automatic display; explicit entry/decline, no lifecycle-triggered browser launch; browser delivery requires a live page |
| Reliable real-task completion / no interruption | Synthetic notice/focus checks; 30-task live acceptance still pending |
| 50-event semantic review | Exact-source audit done; human semantic labels pending |
| User-value / retention hypothesis | No participants or outcome claims |

## Risks / reopen conditions

Proceed to the pilot gate only after installing/reviewing the desired host plugin,
observing a real long turn start and end, collecting 30 independent labeled tasks
at >=95% transition accuracy with no tool-call popup thrashing, and completing the
50-event human audit at >=90% supported key facts. Upgrade rollout compatibility
only when an actual schema mismatch is observed or official trusted hooks are
chosen; do not silently call it cross-host parity.
