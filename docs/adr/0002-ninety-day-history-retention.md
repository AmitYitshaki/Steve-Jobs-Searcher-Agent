# ADR-0002 — 90-day bounded retention on job history

**Status:** Accepted (2026-08-05)

## Context

`jobs_history.json` records the ID of every job ever delivered, to prevent duplicate alerts. Today it is a flat list of string IDs with no timestamps, and it only ever grows — every scan loads the entire set into memory to check membership. At 500+ companies running indefinitely, this is a hard, growth-driven ceiling (the one exception noted in ADR-0001).

Separately, a role that reopens after months of silence is a job worth re-surfacing: employers refresh and repost roles when they don't find a candidate. Re-alerting on it is a *feature*, not a duplicate.

## Decision

Bound job history to a 90-day retention window.

- Migrate the on-disk schema from a flat list of strings to a mapping `{job_id: first_seen_at}` (ISO timestamp).
- Backfill existing legacy string IDs with a `first_seen_at` of the migration timestamp.
- Purge entries older than 90 days.
- **Purge only on the write boundary** (or an explicit maintenance step). `JobHistoryStore.load()` stays pure and read-only — see ADR-0001's no-racing assumption and the Producer's read-only contract.

## Consequences

- History size stabilizes; membership checks stay cheap at scale.
- A role that reappears more than 90 days after its last delivery will re-alert — accepted as desirable product behavior.
- Risk: if any ATS reuses `job_id`s for genuinely different postings, a purge could cause a re-alert for a stale ID. Not observed; revisit if a specific ATS proves to reuse IDs.
- The Producer must never trigger a purge as a side effect of reading; purge lives with the Consumer's writes or a dedicated prune.
