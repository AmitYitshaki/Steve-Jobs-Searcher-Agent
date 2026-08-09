# ADR-0006 — src/-layout with domain-oriented packages

**Status:** Accepted (2026-08-05)

## Context

The codebase grew as a flat directory of modules at the repo root, mixing operational code, tests, manual scripts, runtime state, config, and 139 debug artifacts. Before adding the logical epics (ADR-0004, ADR-0005), the structure is being reorganized so new code lands in a clean layout.

## Decision

Adopt an `src/`-layout with domain-oriented packages and clear separation of code, tests, config, data, and artifacts:

```
src/
  paths.py                     PROJECT_ROOT anchor (top-level module, like pipeline.py)
  models/       results.py (ScrapeResult/ScrapeStatus), job.py (JobRecord)
  scrapers/
    orchestrator.py            Producer: routing + run_scraper
    api/        mappings.py (AtsMapping, ATS_FIELD_MAP), client.py (fetch_ats_jobs)
    browser/    playwright_driver.py, custom_adapters.py
  analysis/
    ai/         analyzer.py (analyze_job, log_cost, prompt building)
    filters/    location.py (LocationFilter)
  storage/
    drivers/    atomic_json.py (AtomicJsonListStore)
    queue.py    (PendingAlertQueue), history.py (JobHistoryStore), health.py (ADR-0005, pending)
  notifications/
    dispatcher.py              Consumer: AlertConsumer
    telegram/   bot.py (TelegramNotifier)
  pipeline.py                  End-to-end runner (launches producer/consumer via `-m`)
tests/        root test_*.py + tests/unit/ + tests/manual/ (consolidation into tests/unit/ pending)
config/       companies.json, prompts/ (agent_*.md, user_profile.md)
data/         jobs_history.json, pending_alerts.json, costs_log.json, scraper_health.json  (gitignored)
logs/         artifacts/ (diagnostic html/png), api_discovery_log.json  (gitignored)
docs/         CONTEXT.md, adr/
```

- Packaging via `pyproject.toml` with an editable install (`pip install -e .`), so `src/` is importable in every context — direct runs, `python -m …`, and pytest — not only under pytest's `pythonpath`.
- Runtime paths anchor to a single `PROJECT_ROOT` constant rather than staying CWD-relative, so module invocation from any directory works.
- The move is behavior-preserving: no logic changes land in the same tickets as relocations; the existing test suite is the green gate.

## Consequences

- Higher one-time blast radius: every import, every `mock.patch` string target, every runtime path literal, and the subprocess invocation in the pipeline must update in lockstep. Sequenced as granular, individually-green migration tickets.
- `costs_log.json` moves into gitignored `data/`; it must be `git rm --cached`ed.
- The 139 gitignored `debug_logs/` artifacts are not migrated — only the code's target directory is repointed.
- New epics (ADR-0004, ADR-0005) build on this layout.
