# CONTEXT — Steve Jobs Searcher Agent

The project's domain glossary and the load-bearing decisions behind its design. Engineering skills read this before exploring; use these terms exactly, and don't re-litigate the decisions recorded in `docs/adr/` without a load-bearing reason.

## What the system is

An autonomous job-discovery agent. It runs unattended (~3×/day, scheduled), scans the career surfaces of a growing set of tech employers (today ~68, target 500+), filters to junior/student software-adjacent roles located in Israel, has each candidate summarized by an LLM, and delivers a Telegram alert — with no duplicate alert ever sent for the same job.

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
- **Scrape-health anomaly** — a per-company signal that scraping itself is degrading (consecutive hard failures, or a drop to zero jobs after previously finding some). Tracked in isolated health state, alerted to an admin surface. See ADR-0005.

## Decisions (see `docs/adr/`)

- **ADR-0001** — File-based JSON state is a deliberate fit for the single-host, ~3×/day SLA, not debt to migrate to a database.
- **ADR-0002** — 90-day bounded retention on job history; schema `{job_id: first_seen_at}`; purge on the write boundary only; `load()` stays pure.
- **ADR-0003** — Stealth over speed: conservative, low-bounded browser concurrency; aggressive parallelism is rejected.
- **ADR-0004** — Every fetch path returns a typed `ScrapeResult`; the foundation for health observability.
- **ADR-0005** — Scraper health is tracked in isolated state (`scraper_health.json`) with tiered anomaly detection, routed to an admin channel — never the candidate job feed.
- **ADR-0006** — `src/`-layout with domain-oriented packages; runtime state in `data/`, config in `config/`, artifacts in `logs/`.
