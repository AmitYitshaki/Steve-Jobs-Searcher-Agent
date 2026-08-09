# Architecture and Code Map

## Project Map — Start Here

This tree was generated from the current checkout after the ADR-0006 migration.
It shows the directories a developer normally needs to understand: application
code, tests, configuration, runtime state, logs, and documentation.

```text
.
|-- src/                                           # Installable application source.
|   |-- paths.py                                   # Defines absolute project/config/data/log paths.
|   |-- pipeline.py                                # Top-level producer/consumer runner and CLI.
|   |-- analysis/                                  # Rules and AI that decide what a job means.
|   |   |-- __init__.py                            # Marks analysis as a Python package.
|   |   |-- ai/                                    # LLM-based job analysis.
|   |   |   |-- __init__.py                        # Marks analysis.ai as a package.
|   |   |   `-- analyzer.py                        # Builds prompts, calls OpenAI, logs token costs.
|   |   `-- filters/                               # Deterministic job eligibility rules.
|   |       |-- __init__.py                        # Marks analysis.filters as a package.
|   |       `-- location.py                        # Accepts/rejects jobs by parsed location.
|   |-- models/                                    # Shared data vocabulary used across layers.
|   |   |-- __init__.py                            # Marks models as a Python package.
|   |   |-- job.py                                 # Defines the shared JobRecord type alias.
|   |   `-- results.py                             # Defines typed browser scrape outcomes.
|   |-- notifications/                             # Alert delivery and transport code.
|   |   |-- __init__.py                            # Marks notifications as a package.
|   |   |-- dispatcher.py                          # Consumes queued alerts and records delivery.
|   |   `-- telegram/                              # Telegram-specific implementation.
|   |       |-- __init__.py                        # Marks notifications.telegram as a package.
|   |       `-- bot.py                             # Sends, sanitizes, retries Telegram messages.
|   |-- scrapers/                                  # Job discovery, routing, and extraction.
|   |   |-- __init__.py                            # Marks scrapers as a Python package.
|   |   |-- orchestrator.py                        # Producer: routes, filters, analyzes, enqueues.
|   |   |-- api/                                   # JSON-based ATS integrations.
|   |   |   |-- __init__.py                        # Marks scrapers.api as a package.
|   |   |   |-- client.py                          # Generic ATS HTTP client and normalizer.
|   |   |   `-- mappings.py                        # Per-ATS URL, method, and field mappings.
|   |   `-- browser/                               # Browser-based scraping integrations.
|   |       |-- __init__.py                        # Marks scrapers.browser as a package.
|   |       |-- custom_adapters.py                  # Eightfold, SuccessFactors, universal adapters.
|   |       `-- playwright_driver.py                # Stealth browser, WAF checks, diagnostics.
|   |-- storage/                                   # Durable local queue and history persistence.
|   |   |-- __init__.py                            # Marks storage as a Python package.
|   |   |-- history.py                             # Stores IDs of successfully delivered jobs.
|   |   |-- queue.py                               # Stores alerts waiting for Telegram delivery.
|   |   `-- drivers/                               # Low-level persistence mechanisms.
|   |       |-- __init__.py                        # Marks storage.drivers as a package.
|   |       `-- atomic_json.py                     # Crash-resistant atomic JSON-list writes.
|   `-- steve_jobs_searcher_agent.egg-info/        # Generated editable-install metadata; not app code.
|       |-- dependency_links.txt                   # Generated package dependency-link metadata.
|       |-- PKG-INFO                               # Generated project name/version metadata.
|       |-- requires.txt                           # Generated installed dependency list.
|       |-- SOURCES.txt                            # Generated package source manifest.
|       `-- top_level.txt                          # Generated importable top-level module list.
|-- tests/                                         # Automated tests and opt-in live checks.
|   |-- unit/                                      # Deterministic pytest suite; external I/O mocked.
|   |   |-- test_alert_queue.py                    # Atomic store, queue, and history behavior.
|   |   |-- test_analyzer.py                       # Prompt construction and mocked OpenAI calls.
|   |   |-- test_location_filter.py                # Location rules and false-positive regressions.
|   |   |-- test_pipeline.py                       # WARP, subprocess, reset, recovery, and CLI flow.
|   |   |-- test_playwright_scraper.py             # WAF, discovery, browser, cleanup, diagnostics.
|   |   |-- test_scraper_adapters.py               # ATS mappings, HTTP client, and adapter routing.
|   |   |-- test_scraper_delivery.py               # Producer filtering, analysis, and enqueueing.
|   |   |-- test_send_alerts.py                    # Consumer delivery and history ordering.
|   |   `-- test_telegram_notifier.py              # Telegram HTML, retry, rate-limit, fallback logic.
|   `-- manual/                                    # Explicit checks that use real external services.
|       |-- manual_playwright_check.py              # Opens a real Microsoft career page in a browser.
|       `-- manual_telegram_check.py                # Sends a real Telegram test message.
|-- config/                                        # Tracked application inputs.
|   |-- companies.json                             # Company URLs, ATS types, and fetch strategies.
|   `-- prompts/                                   # Tracked context supplied to the analyzer.
|       |-- agent_identity.md                      # Defines the analyzer's identity and role.
|       |-- agent_soul.md                          # Defines its behavior and communication style.
|       `-- user_profile.md                        # Defines the target candidate and preferences.
|-- data/                                          # Git-ignored mutable runtime state.
|   |-- costs_log.json                             # OpenAI token usage and estimated costs.
|   |-- jobs_history.json                          # IDs already delivered successfully.
|   `-- pending_alerts.json                        # Durable producer-to-consumer queue.
|-- logs/                                          # Git-ignored runtime diagnostics.
|   `-- artifacts/                                 # Browser HTML/screenshots appear here on failure.
|       `-- .gitkeep                               # Keeps the otherwise-empty directory in Git.
`-- docs/                                          # Architecture, domain, migration, and workflow docs.
    |-- ARCHITECTURE.md                            # This human-readable code map.
    |-- CONTEXT.md                                 # Shared domain glossary and project context.
    |-- migration-handoff.md                       # Completed migration plan and ticket mappings.
    |-- adr/                                       # Permanent architecture decisions.
    |   |-- 0001-file-based-json-state.md          # Why local JSON is the persistence mechanism.
    |   |-- 0002-ninety-day-history-retention.md   # Intended delivered-job retention policy.
    |   |-- 0003-stealth-over-speed-concurrency.md # Why browser stealth wins over concurrency.
    |   |-- 0004-unified-typed-fetch-result.md     # Intended common scraper-result contract.
    |   |-- 0005-isolated-scraper-health-tracking.md # Intended scraper health isolation.
    |   `-- 0006-src-layout-directory-structure.md # Why application code lives under src/.
    `-- agents/                                    # Repository automation workflow guidance.
        |-- domain.md                              # How agents use the domain context.
        |-- issue-tracker.md                       # How repository issues are managed.
        `-- triage-labels.md                       # Canonical issue-triage labels.
```

The `src/steve_jobs_searcher_agent.egg-info/` directory is generated by
`pip install -e .`. A developer normally ignores it; the actual code is in the
Python files and packages above it. Browser runs can additionally create
`logs/api_discovery_log.json` and diagnostic files below `logs/artifacts/`.
Those runtime outputs are not shown as present until they actually exist.

## Where Do I Go to Change Something?

| If you want to change... | Start here |
| --- | --- |
| The complete run order or WARP handling | `src/pipeline.py` |
| Which companies are scanned | `config/companies.json` |
| How a company is routed to a scraper | `src/scrapers/orchestrator.py` |
| An ATS's JSON fields, URL, or request method | `src/scrapers/api/mappings.py` |
| Generic ATS HTTP behavior or response normalization | `src/scrapers/api/client.py` |
| Playwright behavior, WAF detection, or diagnostics | `src/scrapers/browser/playwright_driver.py` |
| Eightfold or SuccessFactors extraction | `src/scrapers/browser/custom_adapters.py` |
| Which job titles are relevant | `src/scrapers/orchestrator.py` |
| Which locations are accepted | `src/analysis/filters/location.py` |
| The LLM call or job-analysis prompt assembly | `src/analysis/ai/analyzer.py` |
| The analyzer's identity or candidate preferences | `config/prompts/` |
| Queue or delivered-history behavior | `src/storage/queue.py` and `src/storage/history.py` |
| How JSON state is safely written | `src/storage/drivers/atomic_json.py` |
| Consumer delivery ordering | `src/notifications/dispatcher.py` |
| Telegram formatting, retries, or API calls | `src/notifications/telegram/bot.py` |
| Any repository-relative location | `src/paths.py` |
| Expected behavior | The matching file in `tests/unit/` |

## The System in One Minute

The application has two deliberately separate phases:

1. The **producer** finds relevant jobs and puts alerts in a durable queue.
2. The **consumer** sends those alerts and records only successful deliveries.

`pipeline.py` runs both phases as Python modules and coordinates the network
state around them:

```text
python -m pipeline
        |
        | disconnect WARP
        v
python -m scrapers.orchestrator                       PRODUCER
        |
        |-- read config/companies.json
        |-- fetch jobs through API clients or Playwright
        |-- filter title and location
        |-- skip jobs already delivered or already queued
        |-- analyze relevant jobs with the LLM
        `-- append alerts to data/pending_alerts.json
        |
        | restore WARP
        v
python -m notifications.dispatcher                    CONSUMER
        |
        |-- read data/pending_alerts.json
        |-- send each alert through Telegram
        |-- on success, add its ID to data/jobs_history.json
        `-- only then remove it from pending_alerts.json
```

This split is important. Scraping can finish even if Telegram is temporarily
unavailable, because unsent work remains in `pending_alerts.json`. Writing the
history before dequeuing also means a crash cannot make a successfully sent job
look unsent.

## Architecture Layers

### `pipeline.py` — Run Coordinator

This is the highest-level entry point. `E2ERunner` does not scrape or send
messages itself. It controls the order and environment in which the two phases
run.

Its responsibilities are:

- optionally reset the queue and history when `--reset-state` is requested;
- disconnect Cloudflare WARP before scraping;
- launch the producer as `python -m scrapers.orchestrator`;
- restore WARP even if the producer fails;
- launch the consumer as `python -m notifications.dispatcher`;
- apply separate timeouts to the producer and consumer;
- provide interactive recovery unless `--non-interactive` is selected.

The child processes use `sys.executable`, so they run with the same Python
interpreter and installed dependencies as the pipeline.

### `paths.py` — Filesystem Map

`paths.py` is the one place that knows where the repository root is. It anchors
`PROJECT_ROOT` from its own installed source location and derives:

```text
PROJECT_ROOT
|-- CONFIG_DIR
|   `-- PROMPTS_DIR
|-- DATA_DIR
`-- LOGS_DIR
    `-- ARTIFACTS_DIR
```

Other modules import these constants instead of relying on the current working
directory. As a result, module execution still finds configuration and state
when launched from an appropriate installed environment.

### `scrapers/` — Job Producer

#### `scrapers/orchestrator.py`

This is the producer's application service. It joins the smaller scraper,
analysis, and storage modules into one scan:

- loads and validates company routes from `config/companies.json`;
- selects a JSON API adapter or browser adapter;
- rejects irrelevant titles and locations;
- deduplicates against delivered history, the existing queue, and the current
  scan;
- asks the analyzer to summarize accepted jobs;
- formats and sanitizes the alert;
- appends a `PendingAlert` to durable storage.

It reads delivered history but never writes it. Delivery history belongs to the
consumer because discovery alone does not prove that a user received an alert.

#### `scrapers/api/mappings.py`

`AtsMapping` describes how a supported JSON ATS represents jobs: request method,
base URL, headers or payload, job-list field, ID/title/location/content fields,
and status filtering. `ATS_FIELD_MAP` stores the concrete mappings, including
the `greenhouse_eu` alias.

When an ATS changes its JSON schema, this is usually the first file to inspect.

#### `scrapers/api/client.py`

This is the only scraper-layer module that imports `requests`. It turns an
`AtsMapping` into a GET or POST request, extracts the mapped fields, and flattens
HTML or nested values into normalized text. Network and response failures are
handled gracefully and currently produce an empty job list.

#### `scrapers/browser/playwright_driver.py`

This module owns browser lifecycle and browser-specific risk:

- launches a stealth-configured Playwright browser context;
- applies realistic browser locale, timezone, viewport, and user-agent values;
- detects WAF or challenge pages;
- waits for useful selectors and extracts job records;
- observes candidate JSON APIs without storing authorization data;
- writes sanitized discovery metadata and failure artifacts;
- always cleans up browser resources;
- returns a typed `ScrapeResult` describing success, no jobs, WAF blockage, or
  failure.

#### `scrapers/browser/custom_adapters.py`

This is the compatibility layer for sites that do not fit the generic JSON ATS
client. It contains the Eightfold, SuccessFactors, and universal Playwright
adapters. Eightfold can try its API and fall back to browser scraping.

### `analysis/` — Relevance and Meaning

#### `analysis/filters/location.py`

`LocationFilter` makes deterministic location decisions before the LLM is
called. It safely inspects location text, titles, and URLs, blocks known foreign
locations, optionally applies a strict allowed-location list, and avoids common
acronym false positives. `LocationDecision` explains the result rather than
returning only an unexplained boolean.

Title-keyword filtering currently remains in `scrapers/orchestrator.py`.

#### `analysis/ai/analyzer.py`

The analyzer loads `agent_identity.md`, `agent_soul.md`, and `user_profile.md`,
adds the scraped job evidence, and asks OpenAI for a concise Telegram-ready
analysis. It logs token usage and estimated cost to `data/costs_log.json`.

This module is the place to change model selection, prompt construction,
response handling, or cost calculation. Human-editable behavioral context stays
in `config/prompts/`, not embedded throughout Python code.

### `storage/` — Durable Local State

#### `storage/drivers/atomic_json.py`

`AtomicJsonListStore` is the low-level safety mechanism behind queue and history
files. It validates that stored data is a JSON list, writes to a temporary file,
flushes it with `fsync`, and atomically replaces the destination. It includes
bounded retries for Windows file-lock behavior.

Higher layers use this driver rather than each inventing their own JSON writing
logic.

#### `storage/queue.py`

`PendingAlert` is the immutable record passed from producer to consumer. It
contains the job ID, company name, job URL, and prepared LLM summary.
`PendingAlertQueue` reads, validates, deduplicates, appends, and removes these
records in `data/pending_alerts.json`.

#### `storage/history.py`

`JobHistoryStore` answers whether a job was already delivered and records new
successful deliveries in `data/jobs_history.json`. Its current representation
is a JSON list of job-ID strings.

### `notifications/` — Alert Consumer

#### `notifications/dispatcher.py`

`AlertConsumer` coordinates storage with an `AlertSender` implementation. For
each queued alert it:

1. removes it immediately if history proves it was already delivered;
2. otherwise attempts delivery;
3. on success, writes history first and then removes the queue entry;
4. on failure, leaves the alert queued for the next run.

`DeliverySummary` reports how many messages were delivered, skipped, or failed.
The dispatcher knows delivery policy but not Telegram HTTP details.

#### `notifications/telegram/bot.py`

`TelegramNotifier` is the concrete transport. It loads credentials from the
environment, sanitizes the limited HTML Telegram accepts, sends messages,
retries transient connection, rate-limit, and server failures with backoff, and
falls back to plain text if Telegram rejects HTML parsing. Its result objects
distinguish successful, permanent, and retry-exhausted outcomes.

### `models/` — Shared Vocabulary

`models/job.py` defines `JobRecord`, the mapping shape exchanged by current
scraper code. `models/results.py` defines the immutable `ScrapeResult` and its
`ScrapeStatus` enum. Keeping these definitions outside a specific scraper avoids
making other modules depend on a browser implementation just to describe a
result.

The package `__init__.py` files are intentionally empty. Imports point to the
module that owns each concept, which makes ownership obvious during searches and
mocking.

## Entry Points and Commands

First install the repository in editable mode so `src/` packages are importable
outside pytest:

```powershell
python -m pip install -e .
```

| Command | What it does | External effects |
| --- | --- | --- |
| `python -m pipeline` | Runs producer and consumer with WARP coordination. | Network, state files, OpenAI, Telegram. |
| `python -m pipeline --reset-state` | Clears queue/history, then performs a full run. | Destructively resets local delivery state. |
| `python -m pipeline --non-interactive` | Runs without WARP recovery prompts. | Aborts if required WARP automation is unavailable. |
| `python -m scrapers.orchestrator` | Runs only discovery, filtering, analysis, and enqueueing. | Network, browser, OpenAI, queue/cost files. |
| `python -m notifications.dispatcher` | Runs only queued Telegram delivery. | Telegram, queue/history files. |
| `python -m analysis.ai.analyzer` | Runs the analyzer's sample invocation. | Can make a live OpenAI call and log cost. |
| `python -m pytest` | Runs automated tests under `tests/`. | External services are mocked. |

On Windows, `python` can be replaced with `py` or the active virtual
environment interpreter. The manual checks are deliberately separate because
they perform real work:

```powershell
python tests/manual/manual_playwright_check.py
python tests/manual/manual_telegram_check.py
```

## Configuration, Data, Logs, and Secrets

### Tracked configuration

| Location | Owner | Purpose |
| --- | --- | --- |
| `config/companies.json` | Scraper orchestrator | Source of truth for companies, ATS types, endpoints, and fetch strategies. |
| `config/prompts/agent_identity.md` | AI analyzer | Defines who the analysis agent is. |
| `config/prompts/agent_soul.md` | AI analyzer | Defines behavior, tone, and operating principles. |
| `config/prompts/user_profile.md` | AI analyzer | Defines the candidate and desired jobs. |

These inputs are version controlled. Changing them changes application behavior
without changing Python code.

### Mutable runtime state

| Location | Written by | Meaning |
| --- | --- | --- |
| `data/pending_alerts.json` | Producer and consumer through the queue | Alerts discovered but not yet successfully delivered. |
| `data/jobs_history.json` | Consumer through the history store | Job IDs confirmed as delivered. |
| `data/costs_log.json` | AI analyzer | OpenAI token and estimated-cost entries. |

The `data/` directory is git-ignored because its contents belong to a particular
runtime instance. Queue and history updates use the storage layer's atomic write
mechanism.

### Diagnostics

| Location | Created by | Meaning |
| --- | --- | --- |
| `logs/api_discovery_log.json` | Playwright response collector | Sanitized candidate API endpoints observed during browser runs. |
| `logs/artifacts/` | Playwright driver | HTML snapshots, screenshots, and related failure evidence. |

`logs/` is git-ignored. Diagnostic HTML and screenshots must be sanitized before
sharing because scraped pages can contain sensitive or session-specific data.
The legacy local `debug_logs/` directory, if present, is not a current write
target.

### Secrets

The root `.env` file commonly supplies `OPENAI_API_KEY`, `TELEGRAM_TOKEN`, and
`TELEGRAM_CHAT_ID`. It is not tracked. Application code receives these values
through the environment; secrets do not belong in `config/companies.json`, the
prompt files, logs, tests, or documentation.

## Testing Map

Each production area has a nearby conceptual test owner:

| Production behavior | Main tests |
| --- | --- |
| Pipeline and module execution | `tests/unit/test_pipeline.py` |
| ATS API mappings/client and adapter routing | `tests/unit/test_scraper_adapters.py` |
| Browser driver, WAF handling, and diagnostics | `tests/unit/test_playwright_scraper.py` |
| Producer filtering and enqueueing | `tests/unit/test_scraper_delivery.py` |
| Location policy | `tests/unit/test_location_filter.py` |
| LLM prompt/response handling | `tests/unit/test_analyzer.py` |
| Atomic store, queue, and history | `tests/unit/test_alert_queue.py` |
| Consumer delivery semantics | `tests/unit/test_send_alerts.py` |
| Telegram transport and retries | `tests/unit/test_telegram_notifier.py` |

`pyproject.toml` declares `src/` as the setuptools package root, exposes
`pipeline` and `paths` as top-level modules, and tells pytest to discover tests
under `tests/`. Automated tests mock HTTP, browser, OpenAI, and Telegram calls.

## Dependency Direction

Higher-level workflow modules depend on focused lower-level modules, not the
other way around:

```text
pipeline
  `-- launches scrapers.orchestrator and notifications.dispatcher

scrapers.orchestrator
  |-- scrapers.api / scrapers.browser
  |-- analysis
  |-- storage
  `-- shared models

notifications.dispatcher
  |-- notifications.telegram
  `-- storage

storage.queue / storage.history
  `-- storage.drivers.atomic_json
```

`paths` is shared filesystem infrastructure and contains no workflow. Storage,
models, and transport code do not import the pipeline or producer. This keeps
the lower-level pieces independently testable and prevents circular ownership.

## Current Code Versus the ADR Roadmap

The architecture decision records include future design targets as well as
completed decisions. This document describes what is implemented now:

- Typed `ScrapeResult` outcomes are used by the Playwright driver. The generic
  API client and custom adapter boundary still return job lists and represent
  failures or no results with an empty list.
- Delivered-job history is currently a flat JSON list of IDs. The richer
  timestamped retention model described by ADR-0002 is not implemented yet.
- ADR-0005 documents scraper-health isolation, but the current tree has no
  scraper-health store or state file.
- Title-keyword filtering and final alert assembly remain in
  `scrapers.orchestrator`; location rules and AI analysis already live in their
  dedicated modules.

Use this file to locate current code. Use [`docs/CONTEXT.md`](CONTEXT.md) for the
domain vocabulary and [`docs/adr/`](adr/) for the reasoning and intended future
direction behind architectural decisions.
