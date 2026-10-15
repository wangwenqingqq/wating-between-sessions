# Research drift bottles — local two-profile pilot

## Scope

The intro-area entry opens an inline, collapsible exchange. This version is
deliberately **same-machine only**, as requested: two independently authenticated
companion instances share a separate local SQLite pool. It is not a public
community, a cloud upload, an account system, or evidence of real peer demand.
There are no seeded members, generated messages, remote requests or model calls.

Each companion data directory represents one local participant. The participant
identity is a random private identifier, not a Codex chat, username or email.
The server obtains it from its own private store, never from the HTTP request.
Peers receive note/reply IDs and relative ownership flags, not identities or
interest profiles. The OS account/pool operator can still inspect local files;
this is not encryption, strong anonymity, or isolation from that OS account.

## Explicit sharing contract

1. Opening the entry only reads this instance's consent state and the field list.
   Selecting fields stays in the page until the user checks consent and submits.
2. Choose 1–5 fields from the displayed catalog. Only matching fields permit
   picking, reading and replying to another participant's bottles. Your own
   bottles are excluded from random picks; an empty pool stays visibly empty.
3. Posting a bottle (1–2,000 characters) and a reply (1–800) each need a separate
   explicit consent. The only submitted text is the corresponding editor value.
   No conversation, source path, project name, timeline or reasoning is attached.
4. Markdown is rendered through the existing local, HTML-disabled renderer.
   Images do not load automatically. No new notification permission is requested,
   and community replies do not automatically open a window or send OS alerts.
5. Only authors may retract their own note/reply. Removing a field retracts the
   participant's notes and replies in that field. Leaving retracts their profile,
   notes and replies; replies by others inside a retracted bottle also disappear.
   Already delivered pages, screenshots and backups cannot be recalled.

Submitting twice with the same request ID returns the same active result.
Consumption hashes survive retraction, field removal and leaving/rejoining, so
late retries cannot resurrect removed text. The receipt table contains only
SHA-256 digests, not bodies, field names, owner IDs or timestamps. A one-time
schema upgrade backfills receipts for active pre-receipt test records. Schema,
backfill and completion marker commit atomically under the same SQLite writer
lock; failures roll back and another instance can retry the migration.

The reading panel and bottle panel collapse independently. Active bottle use
suppresses redundant waiting invitations without sending anything to the Agent.
The original Timeline/Discovery and completion paths remain separate.

## Run two local profiles

From this repository root:

```sh
# Profile A (reuse the usual companion and its private history directory).
python3 demo/app.py start --watch-codex --open

# Profile B: a different data directory and access key; no history import needed.
python3 demo/app.py --data-dir "$HOME/.local/share/between-peer-b" start --open
```

Open **科研漂流瓶** in each instance, choose the same field and explicitly agree
to share it. A posts a clearly labeled test note; B picks and replies; A opens
the note from **我的瓶子与回声** to refresh. Each instance has a different loopback
port and bearer key. Never distribute its runtime file or access key.

Both instances default to `~/.local/share/agent-waiting-bottles/bottles.db`.
For an isolated test pool, set the **same** `AWE_BOTTLE_DIR` directory before
starting both instances. It must be dedicated, non-symlinked and private (`0700`);
the database must be `0600`. Do not point it at an unrelated directory. Restart
all instances after backend/schema changes; mixed-version writers are unsupported.
This adds no new listener, login item, public port or background network service.

The usual history deletion does **not** retract manually shared bottles; use
the separate bottle withdrawal control. Preserve the companion's private data
directory to retain its author identity and retraction ability. There is no
external account recovery. Withdrawal is not secure erasure of backups.

## Bounds and acceptance boundary

- My-content views return at most 50 bottles and 50 authored replies. A bottle
  accepts at most 100 replies. Picking excludes up to 100 already-seen IDs in
  the current page; reloading starts a new picking round.
- The current live-content counters allow 20 bottles and 50 replies per profile
  per rolling day. These prevent accidental bursts, **not adversarial abuse**:
  deletion/rejoining and additional local profiles can circumvent them.
- The loopback API keeps the existing bearer/Host/Origin defenses and bounds
  bottle JSON bodies to 16 KiB; ordinary routes retain their 4 KiB limit.
- Public/cross-device deployment is intentionally not implemented. It requires
  a separately reviewed shared service, account/authentication policy, TLS,
  durable moderation/reporting/blocking, abuse-resistant quotas and operational
  retention/deletion policy. Do not expose the companion or this SQLite pool.

## Reproduce the checks

```sh
python3 -m unittest discover -s tests -v
node --test tests/test_ui.cjs
node --check demo/ui/web/bottles.js
```

The tests use disposable pools and independent profile stores/HTTP servers.
They check consent, same-field round trips, identity non-disclosure, ownership,
retraction/cascades, replay prevention, quotas, concurrency and wire bounds.
Browser QA used two isolated synthetic profiles, not real posted experiences.
No human user-value, anonymity against the operator or production-readiness
claim follows from a passing local integration check.
