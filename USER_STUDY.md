# User study — design only, not conducted

## Admission gate

Do not recruit yet. Require live-host lifecycle acceptance over at least 30 real
tasks (>=95% independently labeled transition accuracy), no repeated popups from
tool activity, end-of-turn reminders observed without focus/scroll interruption,
and human support >=90% on a frozen 50-event sample. A 50/50 record-hash check is
not that semantic audit. Browser-closed notification limitations must be disclosed.

## Planned design

15–30 consenting adult agent users; within-person crossover, balanced randomized
order for comparable long tasks. Freeze host/version, task class, delay threshold,
notification policy, task completion definition, and outcome windows before data
collection. Exclude private/unsafe tasks; users choose their import root and may
delete history or withdraw. No raw conversations leave their machine.

| Arm | Interface | Implementation status |
|---|---|---|
| Control | Ordinary status notice | Not instrumented |
| A | Progress + small game | Not implemented; intentionally beyond first-round MVP |
| B | Progress + personal history | Prototype implemented; not study-qualified |

Primary: post-task subjective waiting-experience rating. Secondary: return to
the agent within a prespecified completion window, voluntary panel close rate,
evidence/card click rate, and self-reported disruption count. Seven-day revisit
is exploratory. Dwell time alone is not a success metric.

Use per-user paired estimates and uncertainty intervals; retain all randomized
orders, exclusions, task durations, notification failures, and negative outcomes.
Do not claim retention improvement from this prototype or a convenience sample.
There is currently **no** telemetry collector, participant recruitment, game,
assignment system, or measured user-study result.

## Real-task acceptance log template

Keep this outside Git and do not include prompt text:

```csv
trial_id,host_version,task_class,expected_start,observed_start,expected_wait_user,observed_wait_user,expected_end,observed_end,panel_opens,focus_interrupted,notification_seen,labeler,notes
```

Count correctness against independent host observation, not this app's own state
as its oracle. Record recoverable tool errors, permissions, aborts, long reasoning,
concurrent sessions, and host crashes. Missing evidence is unknown, not a pass.
