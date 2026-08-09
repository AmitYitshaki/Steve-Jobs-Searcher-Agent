# ADR-0004 — Every fetch path returns a typed ScrapeResult

**Status:** Accepted (2026-08-05)

## Context

Today the fetch paths disagree on their return shape. `PlaywrightJobScraper` returns a typed `ScrapeResult` with a `ScrapeStatus` enum. The JSON-API branches and the HTML adapters return a bare `list[dict]` — and collapse *every* failure (network error, WAF block, malformed response) into `return []`, which is indistinguishable from a genuine "scraped fine, found zero jobs."

This ambiguity blocks scrape-health observability (ADR-0005): anomaly detection cannot tell a broken scraper from a quiet one for ~7 of the 9 ATS paths.

## Decision

Every fetch path returns a typed result carrying status and jobs.

- `ScrapeStatus`: `SUCCESS`, `NO_JOBS`, `WAF_BLOCKED`, `FAILED`, `NETWORK_ERROR`.
- `ScrapeResult`: `status`, `jobs: list[dict]`, and optional error context.
- The type graduates out of `playwright_scraper.py` into shared domain vocabulary (`domain/fetch_result.py`), so it is the contract *every* adapter speaks, not a Playwright detail.

## Consequences

- `NO_JOBS` and `FAILED`/`NETWORK_ERROR` become distinguishable everywhere — the foundation health tracking needs.
- The `ATS_FIELD_MAP` generic fetcher and the HTML adapters must be updated to return `ScrapeResult` instead of `list`; callers that today treat a bare list must unwrap `.jobs`.
- This is sequenced *before* health tracking (ADR-0005), which depends on it.
