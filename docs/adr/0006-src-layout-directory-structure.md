# ADR-0006 — src/-layout with domain-oriented packages

**Status:** Accepted (2026-08-05)

## Context

The codebase grew as a flat directory of modules at the repo root, mixing operational code, tests, manual scripts, runtime state, config, and 139 debug artifacts. Before adding the logical epics (ADR-0004, ADR-0005), the structure is being reorganized so new code lands in a clean layout.

## Decision

Adopt an `src/`-layout with domain-oriented packages and clear separation of code, tests, config, data, and artifacts:

```
src/
  scrapers/   orchestrator.py, ats_mappings.py, playwright_scraper.py, html_adapters.py
  storage/    atomic_store.py, queue_store.py, history_store.py
  alerts/     telegram_notifier.py, alert_consumer.py
  ai/         analyzer.py
  filters/    location_filter.py
  pipeline.py
tests/        mirror src modules
scripts/      manual_*.py
config/       companies.json, prompts/ (agent_*.md, user_profile.md)
data/         jobs_history.json, pending_alerts.json, costs_log.json, scraper_health.json  (gitignored)
logs/         artifacts/ (diagnostic html/png), api_discovery_log.json  (gitignored)
docs/         CONTEXT.md, adr/
```

- Packaging via `pyproject.toml`; tests resolve modules through `pythonpath = ["src"]`.
- Runtime paths anchor to a single `PROJECT_ROOT` constant rather than staying CWD-relative, so module invocation from any directory works.
- The move is behavior-preserving: no logic changes land in the same tickets as relocations; the existing test suite is the green gate.

## Consequences

- Higher one-time blast radius: every import, every `mock.patch` string target, every runtime path literal, and the subprocess invocation in the pipeline must update in lockstep. Sequenced as granular, individually-green migration tickets.
- `costs_log.json` moves into gitignored `data/`; it must be `git rm --cached`ed.
- The 139 gitignored `debug_logs/` artifacts are not migrated — only the code's target directory is repointed.
- New epics (ADR-0004, ADR-0005) build on this layout.
