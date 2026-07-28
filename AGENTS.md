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

# Install Dependencies
py -m pip install -r requirements.txt
py -m pip install beautifulsoup4 lxml playwright
py -m playwright install chromium

# Run Application
py scraper.py           # Full scan
py main.py              # Sample analysis

# Testing & Diagnostics
py test_playwright.py   # Opens an interactive browser
py test_telegram.py     # Sends a real test message

Architecture & Project Structure
scraper.py: The main orchestration engine. Loads companies, filters jobs, tracks history, and coordinates the Telegram alerts. (Transitioning to OOP).

html_adapters.py: Contains BeautifulSoup and Playwright adapters for sites without usable JSON APIs or behind WAFs.

main.py: Builds prompts, calls OpenAI (LLM integration), and records token costs.

companies.json: The source-of-truth company/ATS configuration and pre-filtered URLs.

agent_identity.md, agent_soul.md, user_profile.md: Provide system prompt context for the LLM.

debug_logs/, jobs_history.json, costs_log.json: Runtime state and artifacts. Do not commit generated changes from these files.

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