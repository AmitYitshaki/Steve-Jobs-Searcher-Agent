# CONTEXT — Steve Jobs Searcher Agent

The project's domain glossary and the load-bearing decisions behind its design. Engineering skills read this before exploring; use these terms exactly, and don't re-litigate the decisions recorded in `docs/adr/` without a load-bearing reason.

## What the system is

An autonomous job-discovery agent. It runs unattended (~3×/day, scheduled), scans the career surfaces of a growing set of tech employers (363 companies as of 2026-09-27, no fixed target — catalog growth is gated by relevance, not by a headcount goal), filters to junior/student software-adjacent roles located in Israel, has each candidate summarized by an LLM, and delivers a Telegram alert — with no duplicate alert ever sent for the same job.

## Glossary

- **Producer** — the scan-and-analyze half (`scraper.py` → future `scrapers/orchestrator.py`). Fetches jobs per company, filters, dedupes, LLM-analyzes survivors, and enqueues them. Read-only with respect to job history.
- **Consumer** — the deliver-and-confirm half (`send_alerts.py` → future `alerts/alert_consumer.py`). Reads the pending queue, sends via Telegram, and commits to history *before* dequeuing (crash-safe ordering).
- **ATS** — Applicant Tracking System. The backend behind a company's careers page (Greenhouse, Workday, Amazon, SmartRecruiters, Ashby, SuccessFactors, Eightfold, etc.).
- **`ats_type`** — the per-company config value naming *which* adapter/parsing rules apply.
- **`fetch_strategy`** — the per-company config value naming *how* a company is fetched: `api` (direct JSON) or `browser` (rendered via Playwright). Orthogonal to `ats_type`.
- **Adapter** — a concrete thing that satisfies the fetch interface for one ATS shape at the fetch seam.
- **Universal scraper** — the single stealth-hardened Playwright module (`PlaywrightJobScraper`) shared across all `browser` companies.
- **WAF** — Web Application Firewall / bot challenge (Cloudflare, PerimeterX). The universal scraper is hardened against it (realistic UA/locale/timezone, `playwright-stealth`).
- **`ScrapeResult` / `ScrapeStatus`** — the typed fetch outcome (`SUCCESS`, `NO_JOBS`, `WAF_BLOCKED`, `FAILED`, `NETWORK_ERROR`) every fetch path returns. The vocabulary that distinguishes "scraped fine, found nothing" from "scrape broke." See ADR-0004.
- **Pending alert** — an analyzed job awaiting Telegram delivery, held in `pending_alerts.json` behind `PendingAlertQueue`.
- **Job history** — the set of delivered job IDs (`jobs_history.json` behind `JobHistoryStore`) used for dedup. Subject to a retention window (ADR-0002).
- **Retention window** — the age past which a delivered job ID is purged from history so a reopened role can be re-alerted. See ADR-0002.
- **Scrape-health anomaly** — a per-company signal that scraping itself is degrading (consecutive hard failures, or a drop to zero jobs after previously finding some). Tracked in isolated health state; a company crossing into or out of `degraded`/`failed` triggers a one-line Telegram digest (`_send_health_digest`, ADR-0005), separate from the candidate feed. A company that has never once succeeded stays `unverified` regardless of current errors, so it never triggers the digest — a known, accepted gap, not a bug.
- **Unverified scraper** — a company adapter that has never surfaced a job passing relevance and location checks. It remains a manual-inspection priority even when repeated runs complete without explicit errors.
- **`matches_target_role`** — a seniority-agnostic check (any `TARGET_ROLE_KEYWORDS`/`HEBREW_ROLE_KEYWORDS` match, ignoring `EXCLUDE_KEYWORDS`) used as the catalog-activation gate: a candidate company is only added if it has at least one job, ever, in a target domain (software/data/product/security). Distinct from `is_relevant_job`, which also requires an entry-level signal and is what actually gates candidate alerts.

## Decisions (see `docs/adr/`)

- **ADR-0001** — File-based JSON state is a deliberate fit for the single-host, ~3×/day SLA, not debt to migrate to a database.
- **ADR-0002** — 90-day bounded retention on job history; schema `{job_id: first_seen_at}`; purge on the write boundary only; `load()` stays pure.
- **ADR-0003** — Stealth over speed: conservative, low-bounded browser concurrency; aggressive parallelism is rejected.
- **ADR-0004** — Every fetch path returns a typed `ScrapeResult` (`SUCCESS`/`NO_JOBS`/`WAF_BLOCKED`/`FAILED`). Completed 2026-09-24 across every adapter, including the generic API client, Comeet, and the universal Playwright wrapper (which had been computing the typed result internally all along and silently discarding it).
- **ADR-0005** — Scraper health is tracked in isolated state (`scraper_health.json`) with tiered anomaly detection, routed to the same Telegram destination as the operational heartbeat via a one-line digest sent only on a status change — never mixed into the candidate job feed, and never repeated for a standing anomaly. Implemented 2026-09-24.
- **ADR-0006** — `src/`-layout with domain-oriented packages; runtime state in `data/`, config in `config/`, artifacts in `logs/`.

## Known open items (2026-09-27)

- **Blocked-location markers can beat an explicit Israel signal.** Two companies (Twingate, Personetics) were correctly held out of the catalog because a `"US"`-shaped fragment elsewhere in their location/URL text (`"Remote (US or Israel)"`, `/us/careers/`) trips `LocationFilter`'s blocklist before the explicit Israel option is considered. Same underlying question in both cases; needs one deliberate decision, not a per-company patch.
- **A full relevance sweep of the entire catalog** (including the 235 companies that predate the 2026-09 expansion) using the same `matches_target_role` gate built for step 8 is planned but not yet done.
