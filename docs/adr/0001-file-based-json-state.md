# ADR-0001 — File-based JSON state is deliberate, not debt

**Status:** Accepted (2026-08-05)

## Context

The system persists its two state sets — delivered job history and the pending-alert queue — as local JSON files, read and written through atomic-replace stores (`AtomicJsonListStore`) with Windows file-lock retry. A recurring instinct in architecture reviews is to "upgrade" this to a database for scale.

The operational reality: the agent runs on a single host, as a scheduled background job roughly three times a day, with a total runtime budget of 10–20 minutes. There is no concurrent multi-writer access and no multi-host requirement.

## Decision

Keep file-based JSON state. Do not introduce a database. Atomic temp-file-plus-`os.replace` with bounded lock retry is the correct durability mechanism for this deployment shape.

## Consequences

- The known ceilings of file state (unbounded growth, no cross-process coordination, no multi-host) are accepted because the deployment shape never reaches them — with one exception, unbounded history growth, addressed separately by ADR-0002.
- Overlapping runs are not a supported mode; write-time dedup in `PendingAlertQueue.append()` guards against duplicate *entries*, but the design assumes runs do not race.
- Future reviews should treat "move to a database" as out of scope unless the single-host, ~3×/day SLA itself changes.
