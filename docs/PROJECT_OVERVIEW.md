# Steve Jobs Searcher Agent — Project Overview

An autonomous, AI-driven job-discovery agent. It scans the career surfaces of a
growing set of Israeli tech employers, filters to junior/student
software-adjacent roles, has each surviving candidate summarized by an LLM, and
delivers a de-duplicated Telegram alert — running unattended on AWS EC2.

> This document is the operational and technical overview of the project. It
> covers architecture, deployment, roadmap, observability, configuration,
> recovery, testing, security, and known limitations. For the exhaustive code
> map see [`ARCHITECTURE.md`](ARCHITECTURE.md); for domain vocabulary and
> decisions see [`CONTEXT.md`](CONTEXT.md) and [`adr/`](adr/).

### Project objective and operating model

The service is optimized for a single-host, low-frequency workload: roughly
three scans per day across a growing company catalog. Its primary guarantees
are durable hand-off between discovery and delivery, deterministic filtering
before LLM spend, and retention of failed Telegram deliveries for retry. It is
not a real-time crawler, a distributed queue, or a general-purpose ATS data
platform.

The current production shape is one Docker container on AWS EC2, one scheduler
process, one producer subprocess at a time, one consumer subprocess at a time,
and host-mounted JSON state. This deliberately favors operational simplicity
and stealth over horizontal scale or aggressive concurrency.

---

## 1. Technical Architecture

### 1.1 Producer / Consumer pipeline

The system is deliberately split into two job-processing phases that never
share a process. Job alerts move between them only through a durable on-disk
queue. This separation contains failures and makes queue processing
recoverable. The zero-result operational heartbeat is the one intentional
exception: the producer sends it directly to Telegram because there is no job
alert to enqueue.

```
python -m scheduler            (long-running container entry point)
   │
   ├── Producer  →  python -m scrapers.orchestrator
   │     ├─ load config/companies.json  (routes, ATS type, fetch strategy)
   │     ├─ fetch jobs   (ATS JSON API  ─or─  Playwright browser)
   │     ├─ filter        (title keywords + LocationFilter)
   │     ├─ dedupe        (delivered history ∪ pending queue ∪ current scan)
   │     ├─ analyze       (LLM summary per surviving job)
   │     └─ enqueue       →  data/pending_alerts.json   (PendingAlert)
   │
   └── Consumer  →  python -m notifications.dispatcher
         ├─ read data/pending_alerts.json
         ├─ send each alert via Telegram
         ├─ on success: write history FIRST, then dequeue
         └─ on failure: leave the alert queued for the next cycle
```

**Producer** (`src/scrapers/orchestrator.py`) is read-only with respect to job
history — discovery alone does not prove a user received an alert. It routes
each active company to an adapter, rejects irrelevant titles and blocked
locations, deduplicates against history + the existing queue + the current scan,
asks the analyzer for a concise Hebrew Telegram summary, and appends an
immutable `PendingAlert` to the queue.

**Consumer** (`src/notifications/dispatcher.py`) owns delivery policy. The
ordering is the load-bearing detail: **history is committed before the queue
entry is removed.** If the process dies between those two writes, the next run
recognizes the committed delivery and safely removes the stale queue entry.
This prevents duplication when dequeueing is interrupted. As with any external
message API, there remains a narrow ambiguity window if Telegram accepts a
message and the process dies before the history write; exactly-once delivery
cannot be guaranteed without an idempotency mechanism supplied by Telegram.

**Durable storage** (`src/storage/`) is intentionally file-based JSON
(ADR-0001), sized for a single host running a few times per day. Every mutation
goes through `AtomicJsonListStore`: write to a temp file → `flush` + `fsync` →
atomic `os.replace`, with bounded retries for Windows file-lock contention.

**Failure propagation** is intentionally asymmetric. If the producer exits
non-zero, the scheduler skips the consumer for that cycle. If the consumer
fails, already queued alerts remain on disk for the next run. Per-company
network and parsing errors are generally caught inside adapters so one broken
career site does not abort the full company scan. This also means the producer
can exit successfully while one or more companies were degraded; operators
must read the per-company log lines, not only the final process exit code.

### 1.2 Scrapers — ATS-specific and browser

Companies are routed by two orthogonal config values: `ats_type` (which parsing
rules) and `fetch_strategy` (`api` vs `browser`).

| Path | Mechanism | Examples |
| --- | --- | --- |
| **Declarative JSON ATS** | `ATS_FIELD_MAP` maps each ATS to request method, URL, envelope, and field extractors; one generic `requests`-based client normalizes the result. | Greenhouse, Workday, Ashby, SmartRecruiters, Amazon Jobs |
| **Custom adapters** | Purpose-built extractors for non-generic shapes. Eightfold tries its JSON API then falls back to the browser. | Eightfold, SuccessFactors |
| **Universal Playwright** | A single stealth-hardened browser scraper shared by every `browser` company and used as the universal fallback. | all `custom` / unmapped sites |

The universal scraper (`src/scrapers/browser/playwright_driver.py`) is hardened
against WAF/bot challenges (ADR-0003 — stealth over speed): realistic
user-agent, viewport, `Asia/Jerusalem` timezone and locale, plus
`playwright-stealth`. It ships three cooperating components:

- **`WafChallengeDetector`** — classifies Cloudflare/PerimeterX challenge pages
  from known markers, challenge text, HTTP status, and sparse-content heuristics.
- **`NetworkResponseCollector`** — passively records candidate public job APIs
  observed during a render, with secret-looking query values redacted before
  they touch disk.
- **Typed outcomes** — every browser fetch returns a `ScrapeResult` carrying a
  `ScrapeStatus` (`SUCCESS`, `NO_JOBS`, `WAF_BLOCKED`, `FAILED`), so
  browser-level "scraped fine, found nothing" can be distinguished from "the
  scrape broke" (ADR-0004).

This typed contract is not yet universal. The generic API client,
SuccessFactors adapter, and the compatibility wrapper exposed to the
orchestrator still return plain job lists and collapse both a legitimate empty
response and many failures to `[]`. Extending `ScrapeResult` across every fetch
path is a prerequisite for reliable per-company health reporting.

### 1.3 Deterministic filtering and LLM analysis

Title relevance is decided by keyword tiers (strong/weak entry-level signals ×
target-role keywords, in English and Hebrew) with an exclusion blacklist
(`senior`, `manager`, `principal`, …). Geography is decided **before** any LLM
cost by `LocationFilter`, which blocks known foreign locations found in the
title or URL while avoiding acronym false positives.

Survivors reach `analysis/ai/analyzer.py`, which assembles a system prompt from
human-editable context files (`config/prompts/`) plus the verified job evidence,
calls OpenAI, and logs token usage and estimated cost to `data/costs_log.json`.
Prompt files are loaded through a fault-tolerant reader: a missing context file
(e.g. the gitignored personal profile on a fresh server) degrades to a generic
fallback prompt with a logged warning rather than crashing the cycle.

LLM failures are isolated per job. A failed analysis is logged and that job is
not enqueued, while analysis continues for the remaining candidates. Cost
records are operational telemetry rather than delivery state; failure to retain
them must never be used to infer whether a Telegram alert was sent.

### 1.4 Docker-based deployment

The agent ships as a single container built on
`mcr.microsoft.com/playwright/python:v1.62.0-jammy` — the base image version is
pinned to match the pinned `playwright==1.62.0` dependency, so the bundled
browser binaries always match the library.

Key production properties of the image and compose stack:

- **Editable install** (`pip install -e .`) so the `src/`-layout packages and
  the `paths` / `pipeline` / `scheduler` top-level modules import cleanly under
  `python -m`.
- **Non-root by reusing `pwuser` (UID/GID 1000)** — the base image already
  ships this user at 1000, which matches the default EC2 host user, so
  bind-mounted `./data` and `./logs` stay writable without host-side `chown`
  gymnastics (and without colliding on UID 1000).
- **Bind-mounted state** — `./data`, `./logs`, and `./config` are mounted so
  runtime state, diagnostics, and (gitignored) personal config live on the host
  and survive image rebuilds.
- **`restart: unless-stopped`** — the scheduler is a long-running process, so
  the container is expected to stay up.
- **Log rotation** — the `json-file` driver is capped at `max-size: 10m`,
  `max-file: 3` to protect the EC2 disk over time.

The complete `./config` mount replaces `/app/config` from the image at runtime;
it does not merge directory contents. Therefore the EC2 host must contain
`config/companies.json` and any desired prompt files. Missing prompt files now
fall back safely, but a missing or empty company catalog prevents useful work.
Secrets are injected through `.env`; `.env`, runtime data, and logs are excluded
from the image build context. Private-key files are ignored by Git, but the
current `.dockerignore` does not yet exclude `*.pem`, and it also does not
exclude the private `config/prompts/user_profile.md`. Production builds must not
run with either file in the build context until explicit Docker ignore rules or
an external build context are used.

### 1.5 The subprocess-based watchdog

The `AutonomousScheduler` (`src/scheduler.py`) is the container entry point. It
runs one cycle immediately on start, registers an 8-hour interval, then polls
every 60 seconds. Crucially, it does **not** run the producer and consumer
in-process — it launches each phase as an isolated subprocess under a hard
timeout:

| Phase | Module | Timeout |
| --- | --- | --- |
| Producer | `scrapers.orchestrator` | 900 s |
| Consumer | `notifications.dispatcher` | 300 s |

If a scrape hangs (a stalled Playwright navigation, an unresponsive host), the
timeout **force-terminates the subprocess** and the phase returns exit code
`124`; the scheduler logs it and stays alive for the next cycle. This is why a
subprocess is used rather than a thread watchdog: a Python thread blocked inside
a native Playwright call cannot be forcibly killed, whereas a child process can.
Resilience is layered — the cycle body, the poll loop, and each phase launch are
each wrapped so no single failure can take the container down.

The scheduler launches the consumer only after a zero exit code from the
producer. A non-zero consumer exit is logged but does not delete its undelivered
queue entries. Exit code `127` represents a phase that could not be launched;
`124` represents a watchdog timeout.

### 1.6 Production scheduler vs. local pipeline runner

There are two top-level orchestration modes with different purposes:

| Entry point | Intended environment | Behavior |
| --- | --- | --- |
| `python -m scheduler` | Docker / EC2 | Runs immediately and every eight hours; launches producer and consumer directly as bounded subprocesses. |
| `python -m pipeline` | Local Windows operation | Runs one end-to-end cycle and coordinates Cloudflare WARP: disconnect before scraping, reconnect before Telegram delivery, and always attempt restoration on exit. |

The Docker `CMD` uses `scheduler`, not `pipeline`. Production therefore does
not depend on `warp-cli` or an interactive WARP recovery prompt. The local
pipeline supports `--non-interactive` and `--reset-state`; the latter is a
destructive operator action because it clears both pending alerts and delivered
history.

### 1.7 Runtime state and invariants

| Path | Owner | Meaning | Persistence rule |
| --- | --- | --- | --- |
| `config/companies.json` | Operator / producer | Company routes, ATS type, fetch strategy, selectors, and location filters. | Tracked configuration; mounted read-only in concept, although Compose does not currently enforce read-only mode. |
| `config/prompts/*.md` | Operator / analyzer | Agent identity, behavior, and candidate profile. | Identity/soul may be tracked; personal profile is gitignored and provisioned on the host. |
| `data/pending_alerts.json` | Producer + consumer | Durable jobs waiting for Telegram delivery. | Never clear during normal deployment or restart. |
| `data/jobs_history.json` | Consumer | IDs whose delivery was committed. | Source of deduplication truth; current schema is a flat ID list. |
| `data/costs_log.json` | Analyzer | OpenAI token and estimated cost records. | Diagnostic/accounting data, not workflow state. |
| `logs/api_discovery_log.json` | Browser collector | Sanitized candidate job API endpoints. | Diagnostic and gitignored. |
| `logs/artifacts/` | Playwright | Sanitized HTML, screenshots, and navigation metadata for degraded browser runs. | Diagnostic and gitignored; sanitize again before external sharing. |

The queue and history must be backed up together when taking an operational
snapshot. Restoring only one can produce either duplicate alerts or silently
skipped work.

---

## 2. Roadmap Highlights

The project evolved from a single scraping function into a hardened, containerized
production service. The milestones below trace that path.

| Date / stage | Milestone | What changed |
| --- | --- | --- |
| **2026-07-28 — Foundation** | First end-to-end Python workflow | Procedural functions normalized titles, filtered relevance and location, routed configured companies across ATS/custom adapters, invoked the LLM, and sent Telegram messages. The first commit already included Playwright and a multi-company catalog, but responsibilities and state transitions were coupled. |
| **2026-07-28 — Browser and transport hardening** | OOP Playwright engine, WAF detection, API discovery, Telegram retries | Introduced `PlaywrightJobScraper`, typed browser outcomes, challenge detection, sanitized network discovery, and a retry-aware Telegram notifier with deterministic unit tests. |
| **2026-07-29/30 — Delivery reliability** | Durable Producer/Consumer hand-off | Added the pending-alert queue, delivered history, Windows-safe atomic replacement, strict location filtering, Telegram HTML sanitization, and structured logging. Scraping no longer depended on immediate Telegram availability. |
| **2026-08-04/05 — Modularization** | Stealth stabilization and declarative ATS layer | Hardened browser settings and converted stable JSON integrations into the data-driven `ATS_FIELD_MAP` deep module instead of per-company request code. Microsoft moved onto the universal Playwright path. |
| **2026-08-09/10 — Architecture (ADR-0006)** | `src/`-layout refactor | Introduced domain-oriented packages (`scrapers`, `analysis`, `notifications`, `storage`, `models`) and module-based entry points. Runtime state moved to `data/`, configuration to `config/`, diagnostics to `logs/`, and automated tests to `tests/unit/`. |
| **2026-08-13 — Containerization** | Production Docker infrastructure and autonomous scheduler | Added `Dockerfile`, `.dockerignore`, `docker-compose.yml`, pinned Playwright dependencies, non-root execution, persistent mounts, and `scheduler.py`, making the service reproducible and deployable on EC2. |
| **2026-08-13 — Stability** | Subprocess watchdog | Each phase became a separately killable subprocess with a 900-second producer timeout and 300-second consumer timeout, preventing a stuck scrape from permanently blocking future schedules. |
| **2026-08-13 — Security hardening** | Private-key cleanup and ignore rules | Removed host key material from repository tracking and added `*.pem` to `.gitignore`; `.env` and runtime artifacts remain excluded from Git and the Docker build context. Previously exposed credentials or keys must still be rotated outside the repository. |
| **2026-08-13 — Production** | AWS EC2 runtime | The container runs unattended under Docker Compose, starts a cycle immediately, repeats every eight hours, preserves host-mounted state, restarts unless explicitly stopped, and rotates container logs. |
| **2026-08-13 — Observability** | Zero-result heartbeat | A cycle with no new relevant jobs emits `Scraping cycle completed. 0 new jobs found.` when Telegram credentials are available. It distinguishes an alive producer from total silence, but does not certify every company adapter as healthy. |
| **2026-08-13 — Resilience fix** | Gitignored prompt/profile fallback | Production exposed a `FileNotFoundError`: the personal `user_profile.md` was intentionally gitignored and absent from the server, while the config mount shadowed image contents. The analyzer now warns and falls back to generic prompts so jobs can still be analyzed and queued. |

**Next on the roadmap** (tracked but not yet implemented):

- **Broader ATS coverage** — promote `comeet`, `phenom`, `jobvite`,
  `oracle_recruiting_cloud`, and `greenhouse_embedded` companies off the generic
  browser fallback onto reliable JSON-API adapters with full job content.
- **Scraper-health observability (ADR-0005)** — isolated per-company health
  tracking with tiered anomaly detection (consecutive failures, or a drop to
  zero jobs after previously finding some), routed to an admin channel rather
  than the candidate feed.
- **Bounded history retention (ADR-0002)** — a 90-day `{job_id: first_seen_at}`
  schema so a re-opened role can be re-alerted.
- **Unified result contract (ADR-0004 completion)** — make API and custom
  adapters return typed statuses instead of collapsing errors and empty
  results into the same `[]` value.
- **Production health checks and alert separation** — add a Docker healthcheck,
  restart-count monitoring, and a dedicated admin/operations destination so
  heartbeats and scraper failures do not share the candidate job feed.
- **Secrets and backup automation** — use an EC2-appropriate secret store or
  protected environment provisioning, and automate encrypted snapshots of the
  queue/history pair before deployment changes.

---

## 3. Log Analysis Guide

### 3.1 Where the logs live

The container writes all output to stdout (with `PYTHONUNBUFFERED=1`, so lines
appear live). On the EC2 host:

```bash
docker compose ps
docker compose logs -f --tail 100 --timestamps steve_jobs_agent
docker compose logs --tail 200 --timestamps steve_jobs_agent
docker compose logs --since 8h --timestamps steve_jobs_agent
```

Logs are captured by Docker's `json-file` driver and rotated at 10 MB × 3 files,
so history is bounded — for long-term retention, ship them off-box. `docker
compose ps` should be checked first because a restart loop can make recent log
output look like several normal startup sequences.

Browser diagnostics are separate from the stdout stream and persist through
the `./logs:/app/logs` mount:

```text
logs/api_discovery_log.json
logs/artifacts/<company_id>.html
logs/artifacts/<company_id>.png
logs/artifacts/<company_id>_diagnostic.json
```

The diagnostic JSON is the quickest artifact to inspect: it records HTTP
navigation status, whether a WAF was detected, the detection reason, and the
UTC capture time. HTML and screenshots can still contain personal or session
context despite built-in redaction and must be reviewed before sharing.

### 3.2 Reading a cycle

A healthy cycle has a predictable skeleton. These lifecycle lines come from the
scheduler and are your anchors:

```
INFO - Scheduler started; job searches will run every 8 hours.
INFO - Starting scheduled Steve Jobs search cycle.
INFO - Starting Producer scraping phase: scrapers.orchestrator
  ... per-company scraping output ...
INFO - Starting Consumer alerting phase: notifications.dispatcher
INFO - Scheduled Steve Jobs search cycle completed.
INFO - Next job-search cycle scheduled in 8 hours.
```

Per-company scraping status uses a consistent emoji vocabulary:

| Symbol | Meaning |
| --- | --- |
| 🔍 `Scanning <Company> (ATS: <type>)` | Started fetching this company. |
| 🕵️ `מפעיל סורק אוניברסלי (Playwright)` | Falling back to the universal browser scraper. |
| 🚫 `Rejecting <id>: blocked foreign location …` | A job was filtered out by `LocationFilter`. |
| ⚠️ `<id> החזיר 0 משרות` | Browser navigation completed but extraction found no matching links (`NO_JOBS`); this can be legitimate or a stale selector. |
| 🛡️ `<id> נחסם … WAF` | A bot/WAF challenge blocked the page (`WAF_BLOCKED`). |
| ❌ `שגיאה בסריקה … <id>` | The scrape itself failed (`FAILED`). |
| ✅ `נמצאו N משרות חדשות רלוונטיות` | N new jobs passed all filters and go to analysis. |

The cycle ends with a performance report (site-scan time, AI/analysis time,
total) and the consumer's tally: `X נשלחו, Y נכשלו, Z דולגו`
(sent / failed / skipped).

### 3.3 ATS failure reports

Failures are not all equal. The message tail tells you the class:

| Log fragment | Class | Typical cause |
| --- | --- | --- |
| `No job links matched universal rules` | `NO_JOBS` | The page rendered but no anchor looked like a job link — often a genuine empty result or a site needing a configured selector. |
| `No job links matched configured selector '…'` / `Selector … not found in time` | `NO_JOBS` | The configured CSS selector is stale or the SPA did not render in time. |
| `Eightfold API returned no usable jobs … using Playwright fallback` | Fallback warning | The preferred JSON path was empty; judge the event by the following Playwright result. |
| `Eightfold API unavailable … using Playwright fallback` | Fallback warning | API/network parsing failed but automatic browser recovery started. Actionable only if the fallback also fails repeatedly. |
| `API returned 401/403/422` | API degradation | The endpoint requires a changed payload, route, or authentication behavior; common mappings report this without aborting the full scan. |
| `Network error on <company>: <status>` | API failure | Unexpected non-2xx response. Compare across companies to separate one stale adapter from a host-wide network problem. |
| `net::ERR_NAME_NOT_RESOLVED` | `FAILED` | DNS/URL problem — usually a wrong or dead `api_url` in `companies.json`. |
| `net::ERR_TOO_MANY_REDIRECTS` | `FAILED` | The career URL redirect-loops for a headless client; the target URL likely needs updating. |
| `Page.content: … page is navigating` | Warning | Diagnostics could not be captured because the page was still moving; secondary to the real error on the next line. |
| `Prompt file not found … falling back` | Degraded analysis | Availability is preserved, but candidate-specific analysis may be less accurate until the host prompt is provisioned. |
| `Heartbeat delivery did not succeed` | Operational notification failure | The scrape path continued, but the liveness signal did not reach Telegram. Check credentials and Telegram transport logs. |
| `Producer phase exited with code 124` | Watchdog timeout | The 900-second producer limit was reached and delivery was skipped for the cycle. |
| `Alert delivery exited with code …` | Consumer failure | Pending entries remain queued. Inspect the consumer tally and Telegram status. |

### 3.4 Noise vs. real system errors

The single most important skill when reading these logs is separating **expected
signal** from **actionable faults**.

**Expected — not errors:**

- 🚫 `Rejecting … blocked foreign location` — this is the location filter
  **working**. A cycle rejecting Budapest/Shanghai/Netherlands roles is behaving
  correctly.
- ⚠️ `החזיר 0 משרות` from a company that genuinely has no matching openings.
- The **heartbeat** message on a zero-result cycle — proof the scheduler is
  alive and reached the zero-new-job branch, not a fault. It is **not** proof
  that all ATS integrations succeeded because several adapters represent
  failures as empty lists.

**Data-quality noise (worth improving, not urgent):**

- The universal Playwright scraper matches links by keyword, so it can surface
  non-jobs — blog posts, "Read More" links, or program blurbs — as candidate
  titles. These indicate a company should move onto a proper ATS adapter, not a
  system outage.

**Real, actionable errors:**

- ❌ `FileNotFoundError` during analysis — a required config/prompt file is
  missing on the host. (Now mitigated by the generic-prompt fallback; still
  worth fixing by placing the real file in the bind-mounted `config/`.)
- `net::ERR_NAME_NOT_RESOLVED` / `ERR_TOO_MANY_REDIRECTS` — a broken company URL
  in `companies.json`.
- A company that **previously returned jobs and now consistently returns 0** —
  the scraper for that ATS has likely broken (the intended trigger for the
  planned scraper-health alerts, ADR-0005).
- Any `ERROR`/`exception` from the **scheduler** itself, or a phase repeatedly
  exiting `124` (timeout) — investigate the host or the specific hung company.
- `Producer phase exited with code …; skipping alert delivery` — the consumer
  did not run in that cycle, even if older alerts were already pending.
- Repeated consumer failures or a steadily growing `pending_alerts.json` —
  Telegram delivery is degraded and retained work is accumulating.
- `Unroutable active company configurations` or an empty company file — active
  companies cannot be dispatched to an implementation.
- Repeated container restarts, bind-mount permission errors, or no scheduler
  cycle start for more than eight hours while the service is expected to run.

### 3.5 Practical triage sequence

1. Confirm container state and restart behavior with `docker compose ps`.
2. Find the most recent `Starting scheduled Steve Jobs search cycle` line and
   inspect that cycle as a unit rather than searching isolated emoji markers.
3. Confirm whether the producer reached its performance report and whether the
   consumer was launched.
4. Group failures by scope: one company, one ATS family, all browser sources,
   all HTTP sources, or the whole process.
5. For browser failures, correlate the company ID with its diagnostic JSON,
   HTML, screenshot, and discovery log.
6. Check queue growth and the consumer summary before manually retrying
   anything. Never launch a second consumer concurrently with the scheduled
   one.
7. Treat a single transient failure as an observation; escalate repeated
   failures across consecutive eight-hour cycles or failures that affect an
   entire integration family.

### 3.6 Current observability boundary

There is no implemented end-of-run ATS health digest and no
`scraper_health.json` store yet. The final scheduler success line means both
subprocesses returned zero; it does not mean every company returned valid job
data. Until ADR-0004 is completed across all adapters and ADR-0005 is
implemented, the per-company log stream and Playwright artifacts are the
authoritative diagnostic evidence.

---

## 4. Configuration and Extension Guide

### 4.1 Environment variables

Production secrets are loaded from the host `.env` file through Docker
Compose. The application expects:

| Variable | Consumer | Purpose |
| --- | --- | --- |
| `OPENAI_API_KEY` | Analyzer | LLM analysis for new eligible jobs. |
| `TELEGRAM_TOKEN` | Producer heartbeat + consumer | Telegram Bot API authentication. |
| `TELEGRAM_CHAT_ID` | Producer heartbeat + consumer | Destination for operational heartbeat and job alerts. |

Do not print `.env`, include it in an image, or copy it into diagnostics. A
missing Telegram configuration disables the producer heartbeat and prevents
normal consumer construction. A missing or invalid OpenAI key prevents useful
analysis of newly discovered jobs.

### 4.2 Company configuration contract

Each entry in `config/companies.json` describes both what the source is and how
it should be fetched. Important fields are:

| Field | Meaning |
| --- | --- |
| `company_id` | Stable, unique identifier used in job IDs, logs, and artifact names. Changing it invalidates deduplication continuity. |
| `company_name` | Human-readable name shown in logs and Telegram alerts. |
| `ats_type` | Parsing/normalization family, such as `greenhouse`, `workday`, `ashby`, `successfactors`, or a custom label. |
| `api_url` | JSON endpoint or career-page URL consumed by the selected route. |
| `fetch_strategy` | Explicitly selects `browser` for custom/rendered sources; mapped ATS types use the API client. |
| `is_active` | Optional feature flag. `false` keeps configuration without scanning it. |
| `location_filters` | Source-specific location strings used after global location safety checks. |
| `job_selector` | Optional CSS selector for a Playwright source whose job links cannot be identified reliably by universal rules. |
| `selector_timeout_ms` | Optional positive timeout for the configured selector. Invalid values fall back to the driver default. |

Adding a company is a configuration change only when an existing route can
normalize its data correctly. A new ATS response shape belongs in
`scrapers/api/mappings.py` or a dedicated adapter and requires mocked contract
tests. Do not label a custom page as a mapped ATS merely to bypass routing
validation.

### 4.3 Deduplication identity

API adapters normally build IDs from `company_id` plus the ATS's stable job ID.
Browser adapters hash the normalized job URL when no source ID is available.
Changing a `company_id`, canonical URL pattern, or ID extraction rule can make
an existing opening appear new. Such migrations should include an explicit
history compatibility decision rather than silently resetting state.

---

## 5. Operating Runbook

### 5.1 Local development

The supported development environment is Python 3.10+ on Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
py -m pip install -e .
pytest
python -m pipeline --help
```

Run individual phases when isolating behavior:

```powershell
python -m scrapers.orchestrator
python -m notifications.dispatcher
```

These commands can contact live ATS, OpenAI, or Telegram services. Automated
tests mock those boundaries; manual executions should be intentional and use a
safe test destination where appropriate.

### 5.2 First EC2 deployment

1. Clone the repository and provision `.env` outside Git.
2. Ensure host-side `config/companies.json` exists and add the private
   `config/prompts/user_profile.md` if personalized analysis is required.
3. Create persistent `data/` and `logs/` directories writable by UID/GID 1000.
4. Build and start the service with `docker compose up -d --build`.
5. Inspect `docker compose ps` and follow the immediate first cycle with
   `docker compose logs -f --tail 100 --timestamps steve_jobs_agent`.
6. Confirm producer completion, consumer completion, and persistence of state
   under the host-mounted directories.

The scheduler executes immediately at container start. Deployment is therefore
also a production run; credentials, config, and mounts must be ready before the
container is started.

### 5.3 Updating production

Before rebuilding, take a protected snapshot of `data/pending_alerts.json` and
`data/jobs_history.json` together, plus host-only prompt configuration. Then
pull the intended revision, rebuild, and recreate the service. Verify the new
container's immediate cycle before considering the deployment complete.

Do not delete `data/` during image cleanup. Do not use `--reset-state` as a
deployment convenience. The runtime state is intentionally outside the image
and must survive rebuilds, host reboots, and rollbacks.

### 5.4 Recovery rules

- **Producer failed:** fix the configuration, network, or adapter issue and let
  the next cycle rescan. The consumer is skipped by the scheduler for that
  failed cycle.
- **Consumer failed:** preserve the queue. After fixing Telegram connectivity
  or credentials, allow the next scheduled consumer to retry it.
- **Container restarted:** inspect why it restarted; durable queue/history
  should remain intact through the bind mount.
- **Corrupt or inconsistent JSON state:** stop the scheduler before repair,
  preserve the original files, and restore queue/history from the same
  snapshot. Never edit state while a phase may be writing it.
- **Manual retry:** ensure the scheduled service is stopped or definitely idle
  before launching a one-off producer or consumer. Concurrent consumers can
  race around an external send even when local JSON replacement is atomic.
- **Rollback:** restore the previous code/image while keeping compatible host
  state. If a release changed ID or state schema, follow its migration path
  rather than mixing versions blindly.

---

## 6. Testing and QA Strategy

The automated suite is deterministic and isolates all external effects. HTTP
requests, browser contexts, OpenAI calls, Telegram delivery, subprocesses, and
timing dependencies are mocked. Live checks live under `tests/manual/` and are
never part of the normal test run.

Core coverage areas include:

- ATS mapping, request, normalization, routing, and fallback behavior.
- WAF classification, selectors, browser cleanup, diagnostics, and URL
  sanitization.
- Title/location filtering and false-positive regressions.
- LLM prompt construction, missing-file fallback, and cost logging.
- Atomic JSON writes, queue deduplication, and history ordering.
- Telegram HTML sanitization, retries, rate limits, and permanent failures.
- Producer enqueueing, zero-result heartbeat behavior, and analysis failures.
- Consumer sent/failed/skipped outcomes and preservation of failed alerts.
- Scheduler phase ordering, timeouts, launch failures, interval registration,
  and survival after errors.
- Local pipeline WARP recovery, subprocess timeouts, state reset, and exit
  codes.

Minimum release gates are:

```powershell
pytest
python -m pipeline --help
git diff --check
```

For Docker-affecting changes, also build the image and verify an isolated
container startup with non-production credentials and disposable state. A
release is not validated merely because unit tests pass; the Playwright image
version, non-root mount permissions, module imports, and scheduler startup are
deployment-specific integration points.

Manual checks that contact real services must be opt-in:

```powershell
py tests/manual/manual_playwright_check.py
py tests/manual/manual_telegram_check.py
```

Never run live Telegram or OpenAI checks against the production destination as
part of an automated test suite.

---

## 7. Security and Data Handling

- `.env`, `*.pem`, `data/`, runtime logs, and the personal user profile must
  remain outside version control. If a credential or private key ever enters
  Git history, removing the file is not enough; rotate the credential and
  consider history remediation.
- Git ignore rules do not protect Docker build contexts. The current
  `.dockerignore` excludes `.env`, `data/`, and logs, but still needs explicit
  entries for `*.pem` and `config/prompts/user_profile.md`. Until that is fixed,
  remove those files from the build context or build from a sanitized checkout;
  otherwise `COPY . /app` can bake them into an image layer.
- The Docker image runs as non-root. Preserve least privilege on the EC2 host
  and grant the container only the bind mounts it needs.
- Career pages and ATS descriptions are untrusted input. They are normalized
  before use, supplied to the LLM as job evidence rather than instructions,
  and sanitized again for Telegram-compatible HTML. The analyzer has no tool
  execution capability, limiting the impact of prompt-injection text embedded
  in job descriptions.
- The browser discovery collector redacts secret-looking query parameters, and
  failure HTML applies additional sensitive-value redaction. These controls
  reduce exposure but do not make artifacts automatically safe to publish.
- Logs can reveal company URLs, job IDs, titles, error payloads, and operational
  timing. Restrict EC2 log access and sanitize excerpts before posting them in
  issues or pull requests.
- Backups of queue, history, prompts, or `.env` inherit the sensitivity of the
  source files and should be encrypted and access-controlled.
- Telegram heartbeat and candidate alerts currently share the configured chat.
  A future admin-channel split should isolate operational telemetry from the
  candidate-facing feed.

---

## 8. Known Limitations and Architectural Boundaries

1. **Single-host persistence:** JSON files are an intentional fit for the
   current workload, but they are not a multi-writer distributed database. Do
   not scale the same bind-mounted queue across multiple containers.
2. **No absolute exactly-once delivery:** history-before-dequeue handles local
   crash recovery, but a crash after Telegram accepts a message and before the
   history commit can produce a retry.
3. **Incomplete typed outcomes:** API and custom paths still collapse many
   failures into empty lists, so scheduler success and heartbeat delivery are
   weaker signals than per-company health.
4. **No implemented scraper-health store:** ADR-0005 defines the target, but
   consecutive failures and zero-result regressions are not yet persisted or
   summarized automatically.
5. **No 90-day history retention yet:** ADR-0002 describes a timestamped
   retention model; the current history is a flat list and grows without that
   purge policy.
6. **No generalized pagination:** the generic ATS client performs one mapped
   request. Large ATS catalogs, including limited Workday responses, may need
   explicit pagination to guarantee complete coverage.
7. **Browser data can be shallow:** universal extraction primarily discovers
   links and may lack a full job description or precise location. It is less
   accurate than a dedicated ATS integration and can admit non-job links.
8. **No Docker healthcheck:** `restart: unless-stopped` handles process exits,
   but it does not detect an alive scheduler that is no longer producing useful
   cycles. External monitoring or a container healthcheck is still needed.
9. **Heartbeat semantics are limited:** it reports zero *new relevant* jobs,
   which can also mean all results were old, filtered, or returned as empty by
   degraded adapters. It is a liveness clue, not a fleet-health assertion.
10. **Docker build-context gap:** `*.pem` and the private user profile are
    gitignored but not currently dockerignored. A normal `COPY . /app` can
    include host-only sensitive files if they exist during the build.
11. **Hardcoded model economics:** the analyzer's model choice and token prices
    are embedded in code. Cost estimates must be reviewed when model pricing or
    the selected model changes.

These constraints are acceptable for the present single-user EC2 deployment,
but they define the threshold at which the system should evolve toward typed
health events, stronger monitoring, paginated adapters, controlled schema
migrations, and eventually a transactional store.
