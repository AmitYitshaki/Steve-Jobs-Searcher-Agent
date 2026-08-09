# Codex Migration Handoff — `src/` Restructure (Approach B)

Direct migration into the finalized deep hierarchy (ADR-0006). **Execute tickets in order; each ends with the full test suite green.** Do not batch — one ticket, one green suite, one commit.

Line numbers below reference the code state as of 2026-08-05 (Epics 1–4 landed). Re-confirm with a quick read before editing; treat ranges as guides, not literals.

---

## Global reference tables (apply across all tickets)

### A. Module source → destination

| Current | Destination | Notes |
|---|---|---|
| `alert_queue.py` (`AtomicJsonListStore`) | `src/storage/drivers/atomic_json.py` | |
| `alert_queue.py` (`PendingAlert`, `PendingAlertQueue`) | `src/storage/queue.py` | `PendingAlert` lives with the queue |
| `alert_queue.py` (`JobHistoryStore`) | `src/storage/history.py` | |
| `playwright_scraper.py` (`ScrapeResult`, `ScrapeStatus`) | `src/models/results.py` | extracted first (ticket 03) |
| `playwright_scraper.py` (`JobRecord` alias) | `src/models/job.py` | |
| `playwright_scraper.py` (rest) | `src/scrapers/browser/playwright_driver.py` | |
| `html_adapters.py` | `src/scrapers/browser/custom_adapters.py` | |
| `scraper.py` (`AtsMapping`, `ATS_FIELD_MAP`) | `src/scrapers/api/mappings.py` | |
| `scraper.py` (`fetch_ats_jobs`, `normalize_job_content`) | `src/scrapers/api/client.py` | |
| `scraper.py` (keyword lists, `normalize_text`, `contains_phrase`, `is_relevant_job`) | `src/analysis/filters/keywords.py` | |
| `scraper.py` (`is_in_location`) | `src/analysis/filters/location.py` | joins `LocationFilter` |
| `scraper.py` (`run_scraper`, `fetch_jobs_from_company`, `validate_company_routing`, `extract_job_url`, `load_json`) | `src/scrapers/orchestrator.py` | |
| `location_filter.py` (`LocationFilter`) | `src/analysis/filters/location.py` | |
| `main.py` (`analyze_job`, `log_cost`, OpenAI client) | `src/analysis/ai/client.py` | |
| `main.py` (`load_file`, `build_job_analysis_prompt`) | `src/analysis/ai/prompts.py` | |
| `telegram_notifier.py` (`TelegramHtmlSanitizer`) | `src/notifications/telegram/formatters.py` | + `build_job_alert_message` extracted from `scraper.py` |
| `telegram_notifier.py` (rest) | `src/notifications/telegram/bot.py` | |
| `send_alerts.py` | `src/notifications/dispatcher.py` | |
| `e2e_runner.py` | `src/pipeline.py` | |
| `manual_*.py` | `tests/manual/` | imports fixed in ticket 10 |

`src/storage/health.py` (`ScraperHealthStore`) is **not** created by this migration — it belongs to the ADR-0005 epic. Do not scaffold an empty file; the package tree is complete without it until then.

### B. `unittest.mock.patch` string-target rewrites (the silent breakers)

| Old target | New target | Test file |
|---|---|---|
| `alert_queue.os.replace` | `storage.drivers.atomic_json.os.replace` | test_alert_queue |
| `scraper.requests.post` / `scraper.requests.get` | `scrapers.api.client.requests.post` / `.get` | test_scraper_adapters |
| `scraper.logging.warning` | `scrapers.orchestrator.logging.warning` | test_scraper_adapters |
| `scraper.analyze_job` | `scrapers.orchestrator.analyze_job` | test_scraper_delivery |
| `main.load_file` | `analysis.ai.client.load_file` | test_main_analysis |
| `main.log_cost` | `analysis.ai.client.log_cost` | test_main_analysis |
| `playwright_scraper.time.sleep` / `.stealth_sync` / `.LOGGER.*` | `scrapers.browser.playwright_driver.*` | test_playwright_scraper |
| `html_adapters.PlaywrightJobScraper` | `scrapers.browser.custom_adapters.PlaywrightJobScraper` | test_playwright_scraper |
| `e2e_runner.LOGGER` / `e2e_runner.E2ERunner` | `pipeline.LOGGER` / `pipeline.E2ERunner` | test_e2e_runner |

Patch where a name is **looked up**, not where it's defined (e.g. `analyze_job` is patched in `scrapers.orchestrator`, its caller — not in `analysis.ai.client`).

### C. Runtime path relocations (ticket 02)

| Literal | Current site | New location |
|---|---|---|
| `companies.json` | `scraper.py:433` | `config/companies.json` |
| `agent_soul.md`, `agent_identity.md`, `user_profile.md` | `main.py:117-119` | `config/prompts/` |
| `jobs_history.json` | `scraper.py:32`, `alert_queue.py:212` | `data/` |
| `pending_alerts.json` | `scraper.py:33`, `alert_queue.py:166` | `data/` |
| `costs_log.json` | `main.py:11` | `data/` |
| `debug_logs` / `api_discovery_log.json` | `playwright_scraper.py:406`,`:507` | `logs/artifacts/` |
| `STATE_FILES` tuple | `e2e_runner.py:29` | `data/` |

### D. Files to delete (ticket 01)

- `debug_microsoft.html` (repo root — orphan of the removed `scrape_microsoft`)
- `updated_debug_logs.zip` (repo root — stray archive)
- The 139 `debug_logs/*` artifacts are **not** migrated and **not** deleted from disk; they stay gitignored. Only repoint the code's target dir.

---

## Tickets

### 01 — Scaffold packaging, tree, and stale-file cleanup
**Blocked by:** None
- Create `pyproject.toml` with `[tool.pytest.ini_options] pythonpath = ["src"]`, `testpaths = ["tests"]`.
- Create the full `src/` tree with `__init__.py` in **every** package: `models/`, `storage/`, `storage/drivers/`, `scrapers/`, `scrapers/api/`, `scrapers/browser/`, `analysis/`, `analysis/ai/`, `analysis/filters/`, `notifications/`, `notifications/telegram/`. Create `tests/unit/`, `tests/manual/`, `config/prompts/`, `data/`, `logs/artifacts/` (`.gitkeep` in the last three).
- Move `manual_playwright_check.py`, `manual_telegram_check.py` → `tests/manual/` (imports fixed in ticket 10; not collected by pytest).
- **Delete** `debug_microsoft.html`, `updated_debug_logs.zip` (`git rm` if tracked, else `rm`).
- `.gitignore`: add `data/`, `logs/`, `.pytest_cache/`, keep `__pycache__/`; leave the old `jobs_history.json`/`pending_alerts.json`/`debug_logs/` lines until ticket 02 repoints them.
- **No `.py` module moves, no data moves.**

**Green gate:** `python -m pytest -q` unchanged-green; `git status` shows only additions + the two deletions + manual-script moves.

---

### 02 — Relocate runtime data/config paths
**Blocked by:** 01
- Add a `PROJECT_ROOT` anchor (e.g. `src/paths.py` exposing `PROJECT_ROOT`, `DATA_DIR`, `CONFIG_DIR`, `LOGS_DIR`).
- Move files and repoint every literal per **Table C**, resolving through the anchor (not CWD).
- `git rm --cached costs_log.json` (now gitignored under `data/`); keep `config/companies.json` **tracked**.
- Finalize `.gitignore` to the new `data/`, `logs/` locations.
- Update any test asserting a default path (most use tempdirs — audit `test_alert_queue`, `test_playwright_scraper`).

**Green gate:** `python -m pytest -q` green; no bare root-relative `"jobs_history.json"`/`"companies.json"`/`"debug_logs"` literals remain; `git status` shows `costs_log.json` untracked-ignored, `config/companies.json` tracked.

---

### 03 — `models/` (results, job)
**Blocked by:** 01
- Extract `ScrapeStatus` + `ScrapeResult` (`playwright_scraper.py:61-77`) → `src/models/results.py`.
- Extract `JobRecord` alias (`playwright_scraper.py:56`) → `src/models/job.py`.
- Update `playwright_scraper.py` (still at root) to `from models.results import ScrapeResult, ScrapeStatus` and `from models.job import JobRecord`.
- Update `html_adapters.py:8` to import `ScrapeStatus` from `models.results`.
- Update `test_playwright_scraper.py:21` imports to `models.results`.

**Green gate:** `python -m pytest -q` green.

---

### 04 — `storage/` split
**Blocked by:** 01
- Split `alert_queue.py` per **Table A** into `storage/drivers/atomic_json.py`, `storage/queue.py`, `storage/history.py`; `queue`/`history` import `AtomicJsonListStore` from `storage.drivers.atomic_json`. Delete `alert_queue.py`.
- Update importers: `scraper.py:15`, `send_alerts.py:11`, `e2e_runner.py:13`.
- Patch-target rewrite per **Table B** (`alert_queue.os.replace`).
- Split `test_alert_queue.py` → `tests/unit/test_atomic_json.py`, `test_queue.py`, `test_history.py`.

**Green gate:** `python -m pytest -q` green; no `from alert_queue import` anywhere.

---

### 05a — `analysis/filters/` (keywords, location)
**Blocked by:** 01
- Extract keyword lists + `normalize_text` + `contains_phrase` + `is_relevant_job` (`scraper.py:36-117`) → `analysis/filters/keywords.py`.
- Move `location_filter.py` `LocationFilter` → `analysis/filters/location.py`; move `is_in_location` (`scraper.py:125-129`) into the same module. Delete `location_filter.py`.
- Update `scraper.py` imports to pull these from `analysis.filters.keywords` / `analysis.filters.location`.
- `test_location_filter.py` → `tests/unit/test_location.py`; add `tests/unit/test_keywords.py` covering `is_relevant_job` (move any relevance assertions out of scraper tests if present).

**Green gate:** `python -m pytest -q` green.

---

### 05b — `analysis/ai/` (prompts, client)
**Blocked by:** 01, 02 (COSTS path)
- Split `main.py` per **Table A**: `load_file` + `build_job_analysis_prompt` (`main.py:46-106`) → `analysis/ai/prompts.py`; `analyze_job` + `log_cost` + OpenAI client init (`main.py:1-44, 109-156`) → `analysis/ai/client.py`. `client` imports `load_file`, `build_job_analysis_prompt` from `analysis.ai.prompts`. Delete `main.py`.
- Update `scraper.py:22` → `from analysis.ai.client import analyze_job`.
- `test_main_analysis.py` → `tests/unit/test_ai_client.py`; patch-target rewrites per **Table B** (`main.load_file` → `analysis.ai.client.load_file`, `main.log_cost` → `analysis.ai.client.log_cost`).
- Preserve the `if __name__ == "__main__"` sample-analysis block in `client.py`.

**Green gate:** `python -m pytest -q` green; no `import main` / `from main import` remains.

---

### 06 — `notifications/telegram/` (formatters, bot)
**Blocked by:** 01
- Extract `TelegramHtmlSanitizer` (`telegram_notifier.py:22-110`) → `notifications/telegram/formatters.py`. Also extract the inline `telegram_alert` HTML builder from `scraper.py:526-536` into `formatters.py` as `build_job_alert_message(job) -> str` (behavior-preserving — identical output string).
- Move the rest of `telegram_notifier.py` → `notifications/telegram/bot.py`; `bot` imports `TelegramHtmlSanitizer` from `notifications.telegram.formatters`. Delete `telegram_notifier.py`.
- Update `send_alerts.py:12` → `from notifications.telegram.bot import ...`.
- Update `scraper.py`'s `run_scraper` to call `build_job_alert_message(...)` instead of the inline string.
- `test_telegram_notifier.py` → `tests/unit/test_telegram_bot.py`; add `tests/unit/test_telegram_formatters.py` (sanitizer + `build_job_alert_message`). `test_scraper_delivery.py::test_alert_header_uses_safe_html_formatting` must still pass unchanged (it exercises the alert string end-to-end).

**Green gate:** `python -m pytest -q` green.

---

### 07 — `scrapers/browser/` (playwright_driver, custom_adapters)
**Blocked by:** 03
- Move `playwright_scraper.py` (minus results/job, already extracted) → `scrapers/browser/playwright_driver.py`.
- Move `html_adapters.py` → `scrapers/browser/custom_adapters.py`; it imports `PlaywrightJobScraper` from `scrapers.browser.playwright_driver` and `ScrapeStatus` from `models.results`. Delete both originals.
- Update `scraper.py:16-20` → `from scrapers.browser.custom_adapters import scrape_eightfold, scrape_successfactors, scrape_universal_playwright`.
- Patch-target rewrites per **Table B** (`playwright_scraper.*`, `html_adapters.PlaywrightJobScraper`).
- `test_playwright_scraper.py` → `tests/unit/test_playwright_driver.py`; update its `from html_adapters import scrape_universal_playwright` (`:20`) → `scrapers.browser.custom_adapters`. Split out the `custom_adapters` tests currently in `test_scraper_adapters.py` (eightfold/successfactors) → `tests/unit/test_custom_adapters.py`.

**Green gate:** `python -m pytest -q` green; no root-level `playwright_scraper`/`html_adapters` imports remain.

---

### 08 — `scrapers/api/` + `scrapers/orchestrator.py`
**Blocked by:** 04, 05a, 05b, 06, 07
- Extract `AtsMapping` + `ATS_FIELD_MAP` (`scraper.py:154-255`) → `scrapers/api/mappings.py`.
- Extract `fetch_ats_jobs` (`scraper.py:282-366`) + `normalize_job_content` (`scraper.py:132-151`) → `scrapers/api/client.py`; it imports `AtsMapping` from `scrapers.api.mappings`.
- Move the remainder of `scraper.py` (`run_scraper`, `fetch_jobs_from_company`, `validate_company_routing`, `extract_job_url`, `load_json`) → `scrapers/orchestrator.py`, importing from `scrapers.api.mappings` (`ATS_FIELD_MAP`), `scrapers.api.client` (`fetch_ats_jobs`), `scrapers.browser.custom_adapters`, `analysis.filters.location`, `analysis.filters.keywords`, `analysis.ai.client`, `notifications.telegram.formatters`, `storage.queue`, `storage.history`. Delete `scraper.py`. Preserve `if __name__ == "__main__": run_scraper()`.
- Patch-target rewrites per **Table B** (`scraper.requests.*` → `scrapers.api.client.requests.*`; `scraper.analyze_job` → `scrapers.orchestrator.analyze_job`; `scraper.logging.warning` → `scrapers.orchestrator.logging.warning`).
- Split tests: `test_scraper_adapters.py` ATS-fetch/timeout cases → `tests/unit/test_api_client.py` (patching `scrapers.api.client.requests`); routing/unknown-ats/eightfold-routing cases → `tests/unit/test_orchestrator_routing.py`. `test_scraper_delivery.py` → `tests/unit/test_orchestrator_delivery.py` (patch `scrapers.orchestrator.analyze_job`).

**Green gate:** `python -m pytest -q` green; no `import scraper` / `from scraper import` remains.

---

### 09 — `notifications/dispatcher.py` (consumer)
**Blocked by:** 04, 06
- Move `send_alerts.py` → `notifications/dispatcher.py`, importing `storage.queue`, `storage.history`, `notifications.telegram.bot`. Delete `send_alerts.py`. Preserve `if __name__ == "__main__": raise SystemExit(main())`.
- `test_send_alerts.py` → `tests/unit/test_dispatcher.py`; update `from send_alerts import AlertConsumer`.

**Green gate:** `python -m pytest -q` green.

---

### 10 — `pipeline.py`, rewire, and final verification
**Blocked by:** 08, 09
- Move `e2e_runner.py` → `src/pipeline.py`.
- Fix `project_root` (`e2e_runner.py:46-50`) to resolve to **repo root** — now `Path(__file__).resolve().parent.parent` (or reuse `PROJECT_ROOT`).
- Replace subprocess invocation (`:84-88`, `:104-108`, `:215-230`) and rekey `SCRIPT_TIMEOUTS` (`:31-34`): run `[sys.executable, "-m", "scrapers.orchestrator"]` and `[sys.executable, "-m", "notifications.dispatcher"]` with `cwd=repo_root` and `PYTHONPATH` including `src`.
- Update import (`:13`) → `storage.drivers.atomic_json`; confirm `--reset-state` targets the `data/` paths.
- `test_e2e_runner.py` → `tests/unit/test_pipeline.py`; patch-target rewrites per **Table B**; update any assertion on the subprocess command list to expect the `-m module` form.
- Fix imports in `tests/manual/manual_playwright_check.py` and `manual_telegram_check.py` to the new module paths.

**Final green gate (all must pass):**
- [ ] `python -m pytest -q` — whole suite green, **same test count** as pre-migration (nothing silently dropped)
- [ ] `grep -rn 'patch("' tests/` shows no old module names (`scraper.`, `main.`, `send_alerts.`, `alert_queue.`, `e2e_runner.`, root `html_adapters.`/`playwright_scraper.`)
- [ ] `grep -rn 'import scraper\|from alert_queue\|import main\|from send_alerts\|import e2e_runner\|from html_adapters\|from playwright_scraper\|from location_filter\|from telegram_notifier' src tests` returns nothing
- [ ] Smoke: `python -m pipeline --help`; `python -m scrapers.orchestrator` reads `config/companies.json` and writes to `data/`/`logs/`
- [ ] `git status`: `config/companies.json` tracked; `data/`, `logs/` ignored; `costs_log.json`, `debug_microsoft.html`, `updated_debug_logs.zip` gone from tracking

---

## Sequencing

```
01 ─┬─ 02
    ├─ 03 ─────────────── 07 ─┐
    ├─ 04 ──────────────────┬─┼─ 08 ─┐
    ├─ 05a ─────────────────┤ │      ├─ 10
    ├─ 05b ─────────────────┤ │      │
    └─ 06 ──────────────────┴─┴─ 09 ─┘
```

Run sequentially 01 → 10 for safety (several early tickets touch `scraper.py` in place before 08 moves it — sequential avoids merge conflicts). The requested 04a/04b split is realized and extended: the leaf-move phase is decomposed into **05a** (filters), **05b** (ai), **06** (notifications), **07** (browser) — each independently green.
