# Repository Guidelines & Project Overview

## Purpose
Steve Jobs Searcher Agent is an autonomous, AI-driven job scraping system. It actively monitors Applicant Tracking Systems (ATS) and custom career pages of top-tier tech companies. It intelligently filters for Junior and Student positions (Software Engineering, Data, Product) while explicitly excluding Senior/Management roles. Relevant jobs are then analyzed and summarized by an LLM, and real-time formatted alerts are dispatched to a Telegram channel.

## Technology Stack
- **Language:** Python 3.10+
- **Frameworks/Libraries:** Playwright (Headless Web Scraping & WAF bypass), Requests, BeautifulSoup4, lxml.
- **Database:** Local JSON storage for configuration and state management.
- **Environment:** Windows PowerShell (Primary execution environment).

## Setup, Test, and Development Commands
Use Windows PowerShell and the Python launcher for setup and execution:

```powershell
# Setup Virtual Environment
py -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install Dependencies (editable install puts src/ on the path in every context)
py -m pip install -r requirements.txt
py -m pip install beautifulsoup4 lxml playwright
py -m playwright install chromium
py -m pip install -e .

# Run Application (all app code lives under src/, invoked as modules)
python -m scrapers.orchestrator     # Producer: full scan -> data/pending_alerts.json
python -m notifications.dispatcher  # Consumer: deliver queued alerts to Telegram
python -m pipeline                  # End-to-end producer + consumer (WARP toggling)
python -m analysis.ai.analyzer      # Sample LLM analysis

# Testing & Diagnostics
pytest                                       # Full test suite
py tests/manual/manual_playwright_check.py   # Opens an interactive browser
py tests/manual/manual_telegram_check.py     # Sends a real test message

Architecture & Project Structure (see docs/adr/0006 and docs/CONTEXT.md)
src/scrapers/orchestrator.py: Producer orchestration engine. Loads companies, filters jobs, tracks history, enqueues alerts.
src/scrapers/api/: Declarative ATS mapping table (mappings.py) and generic JSON fetcher (client.py).
src/scrapers/browser/: Playwright driver (playwright_driver.py) and custom/WAF HTML adapters (custom_adapters.py).
src/notifications/dispatcher.py: Consumer; delivers queued alerts via src/notifications/telegram/bot.py.
src/analysis/ai/analyzer.py: Builds prompts, calls OpenAI (LLM integration), records token costs.
src/storage/: Atomic JSON stores for pending alerts (queue.py) and delivered-job history (history.py).
src/pipeline.py: End-to-end runner (WARP toggling; launches producer/consumer as modules).
config/companies.json: The source-of-truth company/ATS configuration and pre-filtered URLs.
config/prompts/ (agent_identity.md, agent_soul.md, user_profile.md): System-prompt context for the LLM.
data/ (jobs_history.json, pending_alerts.json, costs_log.json) and logs/artifacts/: Runtime state and diagnostics. Gitignored; do not commit.

Development & Coding Rules
Strict OOP Paradigm: Strongly prefer Object-Oriented Programming. Refactor procedural code into modular classes (e.g., JobScraper, TelegramNotifier, JobFilter) applying SOLID principles.

Big Tech Coding Standards: Follow PEP 8 with four-space indentation. Use snake_case for functions/variables and UPPER_SNAKE_CASE for constants.

Type Hinting & Documentation: All new functions, methods, and classes MUST include Python type hints (-> str, List[Dict]) and descriptive docstrings.

Encoding: Read and write text strictly as UTF-8, paying special attention to Hebrew content and RTL characters.

Robust Error Handling: Implement resilient network handling, graceful fallbacks (e.g., catching ConnectionResetError), and fail-fast mechanisms.

Commits: Use concise, imperative subjects (e.g., Add Ashby pagination support). Keep generated JSON changes out of commits.

Testing Guidelines
Add deterministic tests for filtering and NLP normalization. Name files test_<feature>.py and functions test_<behavior>().

Mocking: Always mock HTTP requests, OpenAI calls, Telegram dispatches, and browser contexts in automated tests to prevent unintended side effects.

Security & Configuration
Store OPENAI_API_KEY, TELEGRAM_TOKEN, and TELEGRAM_CHAT_ID strictly in the .env file. Never commit secrets.

Sanitization: Always sanitize debug HTML, screenshots, logs, and job history files before sharing them in pull requests or external debugging sessions.

## Agent skills

### Issue tracker

Issues live in this repo's GitHub Issues (`gh` CLI). See `docs/agents/issue-tracker.md`.

### Triage labels

Default five canonical labels (needs-triage, needs-info, ready-for-agent, ready-for-human, wontfix). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context — root `CONTEXT.md` + `docs/adr/`. See `docs/agents/domain.md`.
