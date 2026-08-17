# ADR-0005 — Isolated scraper-health tracking with tiered anomaly detection

**Status:** Accepted (2026-08-05)

## Context

The product promise is "you'll hear about relevant jobs." The failure mode that most quietly defeats it is a *silently broken scraper* — a changed selector, a new WAF block, an ATS returning `[]` — which today is indistinguishable from "no new jobs" and invisible in a 60+ company log stream. Users are alerted when a job appears; nobody is alerted when scraping itself degrades.

## Decision

Track scraper health as first-class, isolated state.

- A dedicated `scraper_health.json`, managed by a dedicated `ScraperHealthStore` — **never** mixed into `jobs_history.json` or `pending_alerts.json`.
- Per company, track: `last_success_at`, `consecutive_failures`, `last_job_count`, `historical_avg_job_count`, `last_error_type`.
- Treat adapters that have never surfaced a relevant, location-valid job as
  `unverified`, and flag them prominently in the per-company operational
  summary. A relevant duplicate still proves the scraper works.
- Calculate `historical_avg_job_count` from a rolling window of the latest 20
  successful fetch runs.
- **Tiered / hybrid anomaly detection:**
  - *Hard failures* — 3+ consecutive failed runs (WAF block, HTTP 5xx, timeout) → alert.
  - *Silent breakage* — a company that previously returned >0 jobs drops to 0 for 3 consecutive runs → flag as a probable DOM/selector anomaly.
- **Delivery isolation:** health alerts route to a separate admin channel (or an end-of-run operational digest), never the candidate-facing Telegram job feed.
- Depends on ADR-0004: populating `consecutive_failures` / `last_error_type` requires typed fetch results across all adapters.

## Consequences

- Silent scraper death becomes loud and attributable to a specific company.
- Never-proven adapters remain visible instead of being mistaken for healthy,
  quiet employers.
- Health state and mutation live strictly on execution/write boundaries; read paths stay pure (consistent with ADR-0002).
- Anomaly thresholds are tunable; the baseline (`historical_avg_job_count`) needs a windowing choice at implementation time.
