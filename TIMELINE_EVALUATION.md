# Timeline evaluation — 2026-10-14

## Result and scope

**100 real local Codex sessions produced 223 evidence-linked excerpts.** A frozen
random sample of 50 (seed 42) matched the original record hash and normalized
visible-message excerpt in 50/50 cases. This is an exact-provenance result, **not**
a human semantic-accuracy result or evidence that every assistant claim is true.
The plan's >=90% human fact-support gate remains pending.

The local inventory contained 1,377 rollout files. Selection was newest mtime
first, non-subagent sessions, usable visible text, and at most 16 MiB per file.
Many files were subagent transcripts or had no usable visible excerpts. Large
sessions were excluded, so this sample is not representative of the entire
archive and may underrepresent long research tasks. The live adapter's file-size
boundary differs from the history import boundary.

| Event kind | Count | Interpretation |
|---|---:|---|
| request | 89 | A recorded request, never promoted to an achievement |
| reported_result | 91 | Final assistant text; explicitly labeled not independently verified |
| decision | 1 | Explicit user-choice wording, keyword heuristic |
| open_question | 42 | Historical unresolved/pending wording, not a claim it is open now |
| Total | 223 | Bounded extractive cards, not 223 verified milestones |

Dates, source session IDs, paths, line numbers and record hashes come from actual
records. Topics are heuristic (`research`, `engineering`, `learning`, `general`).
No LLM, embedding service, inferred personal growth, or invented decision was used.
`confidence=1.0` denotes extractive provenance only; it is not a calibrated truth
probability. A session's first request and last reported result may concern
different subtasks; cards are separate, not a causal pairing.

## Reproduction

```sh
python3 demo/app.py import-history --provider codex --limit 100 --consent
python3 experiments/evaluate_history.py
```

The latter creates a 50-row `human-review.csv` inside the private data directory,
with empty `human_supported`/`notes` labels. It is not included in Git. The source
validator reads only indexed records and rechecks hash plus normalized excerpt.
A changed/missing record produces a warning, not a fabricated replacement source.

Incremental validation: 99 unchanged files were reused, one active session was
reprocessed, 223 events remained stable, and the observed run took 0.137 seconds.
Cache validity includes provider, source size/mtime and **per-file** extractor
version. Regression tests cover provider corrections and limited version upgrades.
Stable event IDs preserve read markers on reimport.

## Quality fixes retained from prototype validation

- Removed injected environment-context fragments, attachment scaffolding and
  automation instructions from human-facing excerpts; 0 such context/pwd-prefix
  cards remained in the checked store.
- Skip recognizable credential patterns, including short labeled passwords.
  Arbitrary sensitive prose is not perfectly detectable; local access is not
  authorization to publish content.
- Keep final-message attribution explicit and show original evidence without
  executing Markdown, source URLs, embedded directives or HTML.
- Keep historical unresolved wording distinct from a currently unresolved issue.

## Human audit still required

Have a person label the frozen 50 cards for speaker attribution, date, supported
key fact, non-misleading excerpt scope, and correct kind. Check source context,
not just a matching quote. Retain failures and ambiguous cases. Require >=45/50
supported events before claiming the plan's 90% semantic gate, and separately
report classification mistakes. Do not overwrite the held-out sample after a
failure; revise on a development set and draw a fresh evaluation sample.

