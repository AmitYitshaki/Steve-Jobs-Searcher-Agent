import html
import json
import logging
import os
import re
import time
import unicodedata
from typing import Any, Mapping, Protocol

from dotenv import load_dotenv

from analysis.ai.analyzer import analyze_job
from analysis.filters.location import LocationFilter
from notifications.telegram.bot import TelegramNotifier
from scrapers.api.client import fetch_ats_jobs
from scrapers.api.mappings import ATS_FIELD_MAP
from scrapers.browser.custom_adapters import (
    scrape_eightfold,
    scrape_successfactors,
    scrape_universal_playwright,
)
from paths import CONFIG_DIR, DATA_DIR
from storage.history import JobHistoryStore
from storage.queue import PendingAlert, PendingAlertQueue

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

# טעינת משתני הסביבה
load_dotenv()

HISTORY_FILE = DATA_DIR / "jobs_history.json"
PENDING_ALERTS_FILE = DATA_DIR / "pending_alerts.json"

# Operational heartbeat: proves the scheduler is alive when a scan legitimately
# finds nothing, distinguishing "ran fine, no new jobs" from a silent failure.
HEARTBEAT_MESSAGE = "Scraping cycle completed. 0 new jobs found."


class HeartbeatSender(Protocol):
    """Minimal transport contract used to deliver the zero-result heartbeat."""

    def send(self, message: str) -> Any:
        """Send one operational heartbeat message."""

# חדש: רשימה שחורה - משרות שנדחה מיד גם אם יש בהן מילות סטודנט
EXCLUDE_KEYWORDS = [
    "senior", "lead", "manager", "director", "principal", "head", "vp", "expert", "architect"
]

STRONG_ENTRY_LEVEL_KEYWORDS = [
    "student", "student position", "student role", "working student",
    "student developer", "student software engineer", "student engineer",
    "intern", "internship", "university intern", "research intern",
    "summer intern", "co-op", "coop", "apprentice", "apprenticeship"
]

WEAK_ENTRY_LEVEL_KEYWORDS = [
    "part time", "part-time", "parttime", "junior", "entry level",
    "entry-level", "new grad", "new graduate", "new college grad",
    "college graduate", "recent graduate", "graduate position",
    "graduate program", "early career", "early careers",
    "early in profession", "trainee"
]

TARGET_ROLE_KEYWORDS = [
    "software engineer", "software developer", "software development",
    "backend", "back end", "back-end", "full stack", "full-stack",
    "developer", "development engineer", "r&d engineer",
    "algorithm", "algorithms", "algorithm engineer", "machine learning",
    "ml engineer", "ai engineer", "applied scientist", "research engineer",
    "computer vision", "deep learning", "nlp",
    "data scientist", "data science", "data analyst", "product analyst",
    "business data analyst", "data engineer", "analytics engineer", "data operations",
    "qa engineer", "software qa", "quality assurance", "automation engineer",
    "qa automation", "test automation", "software tester", "software testing",
    "verification engineer", "validation engineer", "v&v engineer",
    "devops", "cloud engineer", "platform engineer", "infrastructure engineer",
    "site reliability", "sre",
    "associate product manager", "product manager intern",
    "student product manager", "technical product manager", "product operations"
]

HEBREW_ENTRY_LEVEL_KEYWORDS = [
    "סטודנט", "סטודנטית", "משרת סטודנט", "משרת סטודנטית", "משרה לסטודנט",
    "משרה לסטודנטית", "התמחות", "מתמחה", "משרה חלקית", "חצי משרה",
    "בוגר", "בוגרת", "ללא ניסיון"
]

HEBREW_ROLE_KEYWORDS = [
    "פיתוח תוכנה", "מהנדס תוכנה", "מהנדסת תוכנה", "מפתח תוכנה", "מפתחת תוכנה",
    "אלגוריתמים", "למידת מכונה", "מדען נתונים", "מדענית נתונים",
    "אנליסט נתונים", "אנליסטית נתונים", "בדיקות תוכנה", "אוטומציה",
    "אבטחת מידע", "סייבר", "ניהול מוצר", "מנהל מוצר", "מנהלת מוצר"
]

def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text).lower()
    text = re.sub(r"[-_/]+", " ", text)
    text = re.sub(r"[^\w\u0590-\u05FF\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()

def contains_phrase(text: str, phrase: str) -> bool:
    normalized_text = normalize_text(text)
    normalized_phrase = normalize_text(phrase)
    pattern = rf"(?<!\w){re.escape(normalized_phrase)}(?!\w)"
    return re.search(pattern, normalized_text) is not None

def is_relevant_job(title):
    # 1. סינון ראשוני: העפת משרות מהרשימה השחורה
    if any(contains_phrase(title, kw) for kw in EXCLUDE_KEYWORDS):
        return False

    # 2. חיפוש מילות סטודנט חזקות
    if any(contains_phrase(title, kw) for kw in STRONG_ENTRY_LEVEL_KEYWORDS + HEBREW_ENTRY_LEVEL_KEYWORDS):
        return True
        
    # 3. שילוב של מילת כניסה חלשה + התאמה מקצועית
    has_weak_entry = any(contains_phrase(title, kw) for kw in WEAK_ENTRY_LEVEL_KEYWORDS)
    has_target_role = any(contains_phrase(title, kw) for kw in TARGET_ROLE_KEYWORDS + HEBREW_ROLE_KEYWORDS)
    
    if has_weak_entry and has_target_role:
        return True
        
    return False

def load_json(filepath):
    if not os.path.exists(filepath):
        return []
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)

def is_in_location(job_location, location_filters):
    if not location_filters or not job_location:
        return True
    job_loc_lower = job_location.lower()
    return any(loc.lower() in job_loc_lower for loc in location_filters)


def validate_company_routing(companies: list[dict]) -> list[str]:
    """Return active company IDs without a configured fetch route."""

    directly_routed_ats_types = frozenset({"successfactors", "eightfold"})
    unroutable_company_ids: list[str] = []

    for company in companies:
        if not company.get("is_active", True):
            continue

        ats_type = company.get("ats_type")
        has_route = (
            ats_type in ATS_FIELD_MAP
            or ats_type in directly_routed_ats_types
            or company.get("fetch_strategy") == "browser"
        )
        if not has_route:
            unroutable_company_ids.append(
                str(company.get("company_id", "<missing>"))
            )

    return unroutable_company_ids


def fetch_jobs_from_company(company):
    ats_type = company.get("ats_type")
    api_url = company.get("api_url")
    company_id = company.get("company_id")

    print(f"🔍 Scanning {company.get('company_name')} (ATS: {ats_type})...")

    if ats_type in ATS_FIELD_MAP:
        return fetch_ats_jobs(company, ATS_FIELD_MAP[ats_type])

    # 1. SuccessFactors (HTML)
    elif ats_type == "successfactors":
        return scrape_successfactors(company)

    # 2. Eightfold API with Universal Playwright fallback
    elif ats_type == "eightfold":
        return scrape_eightfold(str(company_id), str(api_url))

    # 3. Browser-configured career sites (Universal Playwright)
    elif company.get("fetch_strategy") == "browser":
        return scrape_universal_playwright(company)

    # 4. אם מסיבה כלשהי משהו נפל בין הכיסאות
    else:
        logging.warning(
            "No adapter available; skipping company_id=%s ats_type=%s",
            company_id,
            ats_type,
        )
        return []

def extract_job_url(job: Mapping[str, Any]) -> str:
    """Extract the best available job URL from an adapter result."""

    for key in ("url", "job_url", "absolute_url"):
        value = job.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    description = job.get("description", "")
    if not isinstance(description, str):
        return ""
    match = re.search(r'https?://[^\s<>"]+', description)
    if match is None:
        return ""
    return match.group(0).rstrip(".,);]")


def _send_heartbeat(notifier: HeartbeatSender | None) -> None:
    """Notify operators that the cycle succeeded with zero new jobs."""

    if notifier is None:
        return
    try:
        result = notifier.send(HEARTBEAT_MESSAGE)
    except Exception as error:
        logging.warning(
            "Heartbeat delivery raised %s; the cycle still succeeded.",
            type(error).__name__,
        )
        return
    if not getattr(result, "success", True):
        logging.warning("Heartbeat delivery did not succeed.")


def run_scraper(
    queue: PendingAlertQueue | None = None,
    location_filter: LocationFilter | None = None,
    history_store: JobHistoryStore | None = None,
    heartbeat_notifier: HeartbeatSender | None = None,
) -> None:
    """Scan, analyze, and enqueue new jobs without contacting Telegram.

    A successful scan that finds zero new jobs sends an operational heartbeat
    through ``heartbeat_notifier`` (when provided) so an alive but quiet
    scheduler is never mistaken for a silent failure.
    """

    print("🚀 מתחיל סריקת משרות...")
    total_start_time = time.time()  # תחילת המדידה הכוללת
    alert_queue = queue or PendingAlertQueue(PENDING_ALERTS_FILE)
    active_history_store = history_store or JobHistoryStore(HISTORY_FILE)
    active_location_filter = (
        location_filter
        or LocationFilter(strict_mode=False)
    )
    
    companies = load_json(CONFIG_DIR / "companies.json")
    unroutable_company_ids = validate_company_routing(companies)
    if unroutable_company_ids:
        logging.error(
            "Unroutable active company configurations: %s",
            ", ".join(unroutable_company_ids),
        )
    if not companies:
        print("⚠️ קובץ config/companies.json ריק.")
        return

    history = active_history_store.load()
    pending_ids = alert_queue.ids()
    new_jobs_found = []
    queued_job_ids = set()

    # --- שלב 1: סריקת החברות ---
    for company in companies:
        if not company.get("is_active", True):
            continue
            
        jobs = fetch_jobs_from_company(company)
        location_filters = company.get("location_filters", [])
        
        for job in jobs:
            title_match = is_relevant_job(job["title"])
            job_url = (
                extract_job_url(job)
                or str(company.get("api_url", ""))
            )
            if title_match:
                location_decision = active_location_filter.evaluate(
                    job_title=job["title"],
                    job_url=job_url,
                )
                if not location_decision.allowed:
                    match_details = ""
                    if location_decision.matched_location is not None:
                        match_details = (
                            f" '{location_decision.matched_location}'"
                            f" in {location_decision.source}"
                        )
                    print(
                        f"🚫 Rejecting {job['id']}: "
                        f"{location_decision.reason}{match_details}."
                    )
                    continue

            location_match = is_in_location(job["location"], location_filters)
            is_new = (
                job["id"] not in history
                and job["id"] not in pending_ids
                and job["id"] not in queued_job_ids
            )
            
            if title_match and location_match and is_new:
                new_jobs_found.append({
                    **job,
                    "company_name": company.get(
                        "company_name",
                        company.get("company_id", "Unknown"),
                    ),
                    "job_url": job_url,
                })
                queued_job_ids.add(job["id"])

    scraping_end_time = time.time()  # סיום שלב הסריקה

    # --- שלב 2: ניתוח והוספה לתור ---
    if not new_jobs_found:
        print("\n😴 לא נמצאו משרות חדשות רלוונטיות הפעם.")
        _send_heartbeat(heartbeat_notifier)
    else:
        print(f"\n✅ נמצאו {len(new_jobs_found)} משרות חדשות רלוונטיות. מעביר לסטיב...\n")
        
        for job in new_jobs_found:
            print(
                f"🤖 מנתח את: {job['title']} "
                f"במיקום {job['location']}"
            )

            try:
                analysis = analyze_job(
                    job_title=job["title"],
                    job_location=job["location"],
                    job_content=job.get("content", ""),
                )
            except Exception as error:
                print(
                    "❌ ניתוח המשרה נכשל; המשרה לא תיכנס לתור: "
                    f"{type(error).__name__}"
                )
                continue

            telegram_alert = (
                "🚨 <b>משרה חדשה נמצאה: "
                f"{html.escape(str(job['title']), quote=False)}</b> 🚨\n"
                "🏢 חברה: "
                f"{html.escape(str(job['company_name']), quote=False)}\n"
                "📍 מיקום: "
                f"{html.escape(str(job['location']), quote=False)}\n"
                "🔗 קישור: "
                f"{html.escape(str(job['job_url']), quote=False)}\n\n"
                f"{analysis}"
            )
            alert = PendingAlert(
                job_id=job["id"],
                company_name=job["company_name"],
                job_url=job["job_url"],
                llm_summary=telegram_alert,
            )
            if alert_queue.append(alert):
                pending_ids.add(job["id"])
                print(f"✅ המשרה {job['id']} נשמרה בתור ההתראות.")
            else:
                print(f"ℹ️ המשרה {job['id']} כבר קיימת בתור.")
            print("-" * 40)
    
    analysis_end_time = time.time()  # סיום שלב הניתוח
    
    # --- סיכום זמנים ---
    scraping_duration = scraping_end_time - total_start_time
    analysis_duration = analysis_end_time - scraping_end_time
    total_duration = analysis_end_time - total_start_time
    
    print("\n🏁 הסריקה הושלמה.")
    print("⏱️ דו\"ח ביצועים:")
    print(f"   - זמן סריקת אתרים: {scraping_duration:.1f} שניות")
    print(f"   - זמן ניתוח (AI) ושמירה לתור: {analysis_duration:.1f} שניות")
    print(f"   - סך הכל זמן ריצה: {total_duration:.1f} שניות")

if __name__ == "__main__":
    heartbeat_notifier: TelegramNotifier | None = None
    try:
        heartbeat_notifier = TelegramNotifier.from_environment()
    except ValueError as error:
        logging.warning("Heartbeat disabled: %s", error)

    try:
        run_scraper(heartbeat_notifier=heartbeat_notifier)
    finally:
        if heartbeat_notifier is not None:
            heartbeat_notifier.close()
