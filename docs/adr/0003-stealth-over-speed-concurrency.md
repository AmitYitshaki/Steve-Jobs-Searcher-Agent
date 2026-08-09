# ADR-0003 — Stealth over speed in the Producer

**Status:** Accepted (2026-08-05)

## Context

Scaling toward 500+ companies raises the Producer's runtime. The obvious lever is parallelism. But the system has invested heavily in evading WAF/bot detection (realistic user agent, locale, timezone, `playwright-stealth`, Cloudflare WARP toggling, human-paced waits) — and the thing that most reliably triggers a WAF block is a burst of fast, parallel, headless traffic from one IP. Aggressive parallelism is the direct enemy of the stealth posture.

The operational SLA (ADR-0001) already accepts a 10–20 minute runtime.

## Decision

Prefer conservative, human-paced execution over speed.

- **Browser-based companies**: low-bounded concurrency, reusing a single browser instance; serial or a very small number of contexts. Never a stampede.
- **API-based companies**: cheap and low-risk; lightweight batching / a small bounded pool is acceptable.
- Aggressive parallelism is explicitly rejected. If throughput ever becomes a real constraint, prefer spreading companies across *time* (staggered schedules by tier) over widening concurrency.

## Consequences

- Longer but safer scans; the stealth investment stays valid.
- The 500-company target is met by scheduling and modest batching, not by high concurrency.
- Any future concurrency work must justify itself against detection risk, not just wall-clock time.
