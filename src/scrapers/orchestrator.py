import html
import json
import logging
import os
import re
import time
import unicodedata
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol

from dotenv import load_dotenv

from analysis.ai.analyzer import analyze_job
from analysis.filters.location import LocationFilter
from models.results import ScrapeResult, ScrapeStatus
from notifications.telegram.bot import TelegramNotifier
from scrapers.api.client import fetch_ats_jobs
from scrapers.api.mappings import ATS_FIELD_MAP
from scrapers.browser.custom_adapters import (
    scrape_amdocs,
    scrape_comeet,
    scrape_eightfold,
    scrape_elbit,
    scrape_google,
    scrape_iai,
    scrape_meta,
    scrape_oracle_rc,
    scrape_successfactors,
    scrape_thales_phenom,
    scrape_universal_playwright,
    scrape_workable,
)
from scrapers.health import CompanyHealthTracker
from logging_config import configure_logging
from paths import CONFIG_DIR, DATA_DIR
from storage.health import ScraperHealthStore
from storage.history import JobHistoryStore
from storage.queue import PendingAlert, PendingAlertQueue

configure_logging()
LOGGER = logging.getLogger(__name__)

# טעינת משתני הסביבה
load_dotenv()

HISTORY_FILE = DATA_DIR / "jobs_history.json"
PENDING_ALERTS_FILE = DATA_DIR / "pending_alerts.json"
HEALTH_FILE = DATA_DIR / "scraper_health.json"

# Operational heartbeat: proves the scheduler is alive when a scan legitimately
# finds nothing, distinguishing "ran fine, no new jobs" from a silent failure.
HEARTBEAT_MESSAGE = "Scraping cycle completed. 0 new jobs found."
ANOMALY_HEALTH_STATUSES = frozenset({"failed", "degraded"})

Adapter = Callable[[Mapping[str, Any]], ScrapeResult]

CUSTOM_API_ADAPTERS: dict[str, Adapter] = {
    "amdocs": scrape_amdocs,
    "elbit_systems": scrape_elbit,
    "iai": scrape_iai,
    "imperva_thales": scrape_thales_phenom,
}
CUSTOM_BROWSER_ADAPTERS: dict[str, Adapter] = {
    "google_custom": scrape_google,
    "meta_custom": scrape_meta,
}
# Keyed by ats_type (not company_id) like CUSTOM_BROWSER_ADAPTERS, since a
# single adapter here is meant to serve every company sharing that ATS
# platform rather than one company_id at a time.
CUSTOM_API_ADAPTERS_BY_ATS_TYPE: dict[str, Adapter] = {
    "oracle_recruiting_cloud": scrape_oracle_rc,
    "comeet": scrape_comeet,
    "workable": scrape_workable,
}


class OperationalMessageSender(Protocol):
    """Minimal transport contract for producer operational messages."""

    def send(self, message: str) -> Any:
        """Send one operational message."""

# חדש: רשימה שחורה - משרות שנדחה מיד גם אם יש בהן מילות סטודנט
EXCLUDE_KEYWORDS = [
    "senior", "staff", "lead", "manager", "director", "principal",
    "head", "vp", "expert", "architect", "sales", "marketing",
    "human resources", "hr", "business development", "recruiter",
    "recruiting", "talent acquisition", "customer success",
    "account executive",
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
    "college graduate", "recent graduate", "graduate", "graduate position",
    "graduate program", "early career", "early careers",
    "early in profession", "trainee",
    # "grad" is not a prefix of "graduate" under whole-phrase matching, so
    # "Software Engineer, University Grad" matched nothing before these.
    # Safe as weak signals: they still require a target-role match to pass.
    "grad", "university grad", "university graduate", "college grad",
]

TARGET_ROLE_KEYWORDS = [
    "software engineer", "software developer", "software development",
    "software dev engineer", "software dev", "dev engineer",
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


@dataclass(frozen=True)
class TitleDecision:
    """Describe whether a title passed deterministic relevance rules."""

    allowed: bool
    reason: str = ""
    matched_keyword: str | None = None


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

def _first_matching_keyword(
    title: str,
    keywords: list[str],
) -> str | None:
    """Return the first complete keyword phrase found in ``title``."""

    return next(
        (keyword for keyword in keywords if contains_phrase(title, keyword)),
        None,
    )


def _matching_keywords(title: str, keywords: list[str]) -> list[str]:
    """Return every complete keyword phrase found in ``title``."""

    return [
        keyword for keyword in keywords if contains_phrase(title, keyword)
    ]


def _blocking_exclusions(title: str, role_keyword: str | None) -> list[str]:
    """Return exclusions that are not merely part of a target role name.

    ``EXCLUDE_KEYWORDS`` holds seniority and out-of-scope function words, but
    some of them appear inside role names we explicitly target: "manager" is a
    substring of "product manager intern", which ``TARGET_ROLE_KEYWORDS`` lists
    verbatim. Excluding on such a word contradicts our own target list, so an
    exclusion contained in the matched role phrase is discarded. Any exclusion
    outside that phrase ("senior", "sales") still blocks the title.
    """

    exclusions = _matching_keywords(title, EXCLUDE_KEYWORDS)
    if role_keyword is None:
        return exclusions
    return [
        keyword
        for keyword in exclusions
        if not contains_phrase(role_keyword, keyword)
    ]


def is_relevant_job(title: str) -> TitleDecision:
    """Evaluate title relevance while preserving strong-signal recall."""

    role_keyword = _first_matching_keyword(
        title,
        TARGET_ROLE_KEYWORDS + HEBREW_ROLE_KEYWORDS,
    )
    blocking_exclusions = _blocking_exclusions(title, role_keyword)
    if blocking_exclusions:
        return TitleDecision(
            allowed=False,
            reason="excluded title keyword",
            matched_keyword=blocking_exclusions[0],
        )

    strong_keyword = _first_matching_keyword(
        title,
        STRONG_ENTRY_LEVEL_KEYWORDS + HEBREW_ENTRY_LEVEL_KEYWORDS,
    )
    if strong_keyword is not None:
        return TitleDecision(
            allowed=True,
            reason="strong entry-level signal",
            matched_keyword=strong_keyword,
        )

    weak_keyword = _first_matching_keyword(
        title,
        WEAK_ENTRY_LEVEL_KEYWORDS,
    )
    if weak_keyword is not None and role_keyword is not None:
        return TitleDecision(
            allowed=True,
            reason="weak entry-level and target-role signals",
            matched_keyword=weak_keyword,
        )
    if weak_keyword is not None:
        return TitleDecision(
            allowed=False,
            reason="weak entry-level signal without target role",
            matched_keyword=weak_keyword,
        )
    return TitleDecision(
        allowed=False,
        reason="no qualifying entry-level title signal",
    )

def load_json(filepath):
    if not os.path.exists(filepath):
        return []
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)

def is_in_location(job_location, location_filters):
    if not location_filters:
        return True
    if not job_location:
        return False
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
        company_id = str(company.get("company_id", "<missing>"))
        has_custom_api_route = (
            ats_type == "custom"
            and company.get("fetch_strategy") == "api"
            and company_id in CUSTOM_API_ADAPTERS
        )
        # Mirrors the ats_type-keyed branch in fetch_jobs_from_company. Without
        # it, every ATS served by a shared custom adapter (oracle_recruiting_
        # cloud today) is reported unroutable on every run despite routing fine.
        has_custom_api_route_by_ats_type = (
            company.get("fetch_strategy") == "api"
            and ats_type in CUSTOM_API_ADAPTERS_BY_ATS_TYPE
        )
        has_route = (
            ats_type in ATS_FIELD_MAP
            or ats_type in directly_routed_ats_types
            or company.get("fetch_strategy") == "browser"
            or has_custom_api_route
            or has_custom_api_route_by_ats_type
        )
        if not has_route:
            unroutable_company_ids.append(company_id)

    return unroutable_company_ids


def fetch_jobs_from_company(company: Mapping[str, Any]) -> ScrapeResult:
    """Dispatch one company and always expose a typed scrape outcome."""

    ats_type = company.get("ats_type")
    api_url = company.get("api_url")
    company_id = company.get("company_id")

    LOGGER.info(
        "🔍 Scanning %s (ATS: %s)...", company.get("company_name"), ats_type
    )

    custom_api_adapter = CUSTOM_API_ADAPTERS.get(str(company_id))
    if (
        ats_type == "custom"
        and company.get("fetch_strategy") == "api"
        and custom_api_adapter is not None
    ):
        return custom_api_adapter(company)

    custom_api_adapter_by_ats_type = CUSTOM_API_ADAPTERS_BY_ATS_TYPE.get(
        str(ats_type)
    )
    if (
        company.get("fetch_strategy") == "api"
        and custom_api_adapter_by_ats_type is not None
    ):
        return custom_api_adapter_by_ats_type(company)

    custom_browser_adapter = CUSTOM_BROWSER_ADAPTERS.get(str(ats_type))
    if (
        company.get("fetch_strategy") == "browser"
        and custom_browser_adapter is not None
    ):
        return custom_browser_adapter(company)

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
        LOGGER.warning(
            "No adapter available; skipping company_id=%s ats_type=%s",
            company_id,
            ats_type,
        )
        return ScrapeResult(
            status=ScrapeStatus.FAILED,
            jobs=[],
            message=f"No adapter for ats_type={ats_type!r}.",
        )

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


def _send_operational_message(
    notifier: OperationalMessageSender | None,
    message: str,
    message_kind: str,
) -> None:
    """Deliver an operational message without failing the producer run."""

    if notifier is None:
        return
    try:
        result = notifier.send(message)
    except Exception as error:
        LOGGER.warning(
            "%s delivery raised %s; the cycle still succeeded.",
            message_kind,
            type(error).__name__,
        )
        return
    if not getattr(result, "success", True):
        LOGGER.warning("%s delivery did not succeed.", message_kind)


def _send_heartbeat(
    notifier: OperationalMessageSender | None,
) -> None:
    """Notify operators that the cycle succeeded with zero new jobs."""

    _send_operational_message(notifier, HEARTBEAT_MESSAGE, "Heartbeat")


def _health_digest_message(
    previous_state: Mapping[str, Mapping[str, Any]],
    current_state: Mapping[str, Mapping[str, Any]],
) -> str | None:
    """Build one digest for meaningful scraper-health transitions."""

    lines: list[str] = []
    for company_id, current in current_state.items():
        previous = previous_state.get(company_id)
        if previous is None:
            continue

        old_status = str(previous.get("last_status", ""))
        new_status = str(current.get("last_status", ""))
        if old_status == new_status:
            continue
        company_name = str(
            current.get("company_name") or company_id
        )
        if new_status in ANOMALY_HEALTH_STATUSES:
            details = [f"{old_status} -> {new_status}"]
            error_type = current.get("last_error_type")
            if error_type:
                details.append(f"error={error_type}")
            if new_status == "failed":
                details.append(
                    "consecutive failures="
                    f"{current.get('consecutive_failures', 0)}"
                )
            else:
                details.append(
                    "consecutive zero-job runs="
                    f"{current.get('consecutive_zero_job_runs', 0)}"
                )
            lines.append(
                f"🚨 {company_name}: " + " | ".join(details)
            )
        elif (
            old_status in ANOMALY_HEALTH_STATUSES
            and new_status == "healthy"
        ):
            lines.append(
                f"✅ {company_name}: recovered "
                f"({old_status} -> healthy)"
            )

    if not lines:
        return None
    return "Scraper health changes:\n" + "\n".join(lines)


def _send_health_digest(
    notifier: OperationalMessageSender | None,
    previous_state: Mapping[str, Mapping[str, Any]],
    current_state: Mapping[str, Mapping[str, Any]],
) -> None:
    """Send one operational digest when anomaly state changed."""

    message = _health_digest_message(previous_state, current_state)
    if message is None:
        return
    _send_operational_message(
        notifier,
        message,
        "Scraper-health digest",
    )


def run_scraper(
    queue: PendingAlertQueue | None = None,
    location_filter: LocationFilter | None = None,
    history_store: JobHistoryStore | None = None,
    health_store: ScraperHealthStore | None = None,
    heartbeat_notifier: OperationalMessageSender | None = None,
) -> None:
    """Scan, analyze, and enqueue new jobs without contacting Telegram.

    ``heartbeat_notifier`` carries producer operational messages: a heartbeat
    for a successful zero-job cycle and one health digest when anomaly state
    changes. Health delivery never affects candidate-job processing.
    """

    LOGGER.info("🚀 מתחיל סריקת משרות...")
    total_start_time = time.time()  # תחילת המדידה הכוללת
    alert_queue = queue or PendingAlertQueue(PENDING_ALERTS_FILE)
    active_history_store = history_store or JobHistoryStore(HISTORY_FILE)
    active_health_store = health_store or ScraperHealthStore(HEALTH_FILE)
    active_location_filter = (
        location_filter
        or LocationFilter(strict_mode=False)
    )
    
    companies = load_json(CONFIG_DIR / "companies.json")
    unroutable_company_ids = validate_company_routing(companies)
    if unroutable_company_ids:
        LOGGER.error(
            "Unroutable active company configurations: %s",
            ", ".join(unroutable_company_ids),
        )
    if not companies:
        LOGGER.warning("⚠️ קובץ config/companies.json ריק.")
        return

    history = active_history_store.load()
    health_state = active_health_store.load()
    new_health_state = dict(health_state)
    pending_ids = alert_queue.ids()
    new_jobs_found = []
    queued_job_ids = set()

    # --- שלב 1: סריקת החברות ---
    for company in companies:
        if not company.get("is_active", True):
            continue

        company_id = str(company.get("company_id", "<missing>"))
        company_name = str(
            company.get("company_name", company_id)
        )
        previous_company_state = health_state.get(company_id, {})
        tracker = CompanyHealthTracker(
            company_id=company_id,
            company_name=company_name,
            previous_state=previous_company_state,
        )

        try:
            scrape_result = fetch_jobs_from_company(company)
            if scrape_result.status in {
                ScrapeStatus.FAILED,
                ScrapeStatus.WAF_BLOCKED,
            }:
                tracker.record_failure(scrape_result.status.name)
                LOGGER.warning(
                    "Scrape failed for %s (%s): %s",
                    company_id,
                    scrape_result.status.value,
                    scrape_result.message,
                )
                continue
            jobs = scrape_result.jobs
            tracker.record_fetch(len(jobs))
            location_filters = company.get("location_filters", [])

            for job in jobs:
                title_decision = is_relevant_job(job["title"])
                if not title_decision.allowed:
                    tracker.record_title_rejection()
                    match_details = ""
                    if title_decision.matched_keyword is not None:
                        match_details = (
                            f" '{title_decision.matched_keyword}'"
                        )
                    LOGGER.debug(
                        "Rejecting %s: title %s%s.",
                        job["id"],
                        title_decision.reason,
                        match_details,
                    )
                    continue

                job_url = (
                    extract_job_url(job)
                    or str(company.get("api_url", ""))
                )
                location_decision = active_location_filter.evaluate(
                    job_title=job["title"],
                    job_url=job_url,
                )
                if not location_decision.allowed:
                    tracker.record_location_rejection()
                    match_details = ""
                    if location_decision.matched_location is not None:
                        match_details = (
                            f" '{location_decision.matched_location}'"
                            f" in {location_decision.source}"
                        )
                    LOGGER.debug(
                        "Rejecting %s: location %s%s.",
                        job["id"],
                        location_decision.reason,
                        match_details,
                    )
                    continue

                location_match = is_in_location(
                    job["location"],
                    location_filters,
                )
                if not location_match:
                    tracker.record_location_rejection()
                    LOGGER.debug(
                        "Rejecting %s: adapter location %r does not match "
                        "configured filters %r.",
                        job["id"],
                        job["location"],
                        location_filters,
                    )
                    continue

                tracker.record_relevant()
                is_new = (
                    job["id"] not in history
                    and job["id"] not in pending_ids
                    and job["id"] not in queued_job_ids
                )
                if not is_new:
                    tracker.record_duplicate()
                    continue

                tracker.record_new()
                new_jobs_found.append({
                    **job,
                    "company_name": company_name,
                    "job_url": job_url,
                })
                queued_job_ids.add(job["id"])
        except Exception as error:
            tracker.record_failure(error)
            LOGGER.exception(
                "Company scrape failed for %s.",
                company_id,
            )
        finally:
            new_health_state[company_id] = tracker.snapshot()
            LOGGER.info("%s", tracker.summary_line())

    active_health_store.save(new_health_state)
    _send_health_digest(
        heartbeat_notifier,
        health_state,
        new_health_state,
    )

    scraping_end_time = time.time()  # סיום שלב הסריקה

    # --- שלב 2: ניתוח והוספה לתור ---
    if not new_jobs_found:
        LOGGER.info("😴 לא נמצאו משרות חדשות רלוונטיות הפעם.")
        _send_heartbeat(heartbeat_notifier)
    else:
        LOGGER.info(
            "✅ נמצאו %s משרות חדשות רלוונטיות. מעביר לסטיב...",
            len(new_jobs_found),
        )

        for job in new_jobs_found:
            LOGGER.info(
                "🤖 מנתח את: %s במיקום %s", job["title"], job["location"]
            )

            try:
                analysis = analyze_job(
                    job_title=job["title"],
                    job_location=job["location"],
                    job_content=job.get("content", ""),
                )
            except Exception as error:
                LOGGER.error(
                    "❌ ניתוח המשרה נכשל; המשרה לא תיכנס לתור: %s",
                    type(error).__name__,
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
                LOGGER.info("✅ המשרה %s נשמרה בתור ההתראות.", job["id"])
            else:
                LOGGER.info("ℹ️ המשרה %s כבר קיימת בתור.", job["id"])
            LOGGER.info("-" * 40)
    
    analysis_end_time = time.time()  # סיום שלב הניתוח
    
    # --- סיכום זמנים ---
    scraping_duration = scraping_end_time - total_start_time
    analysis_duration = analysis_end_time - scraping_end_time
    total_duration = analysis_end_time - total_start_time
    
    LOGGER.info("🏁 הסריקה הושלמה.")
    LOGGER.info("⏱️ דו\"ח ביצועים:")
    LOGGER.info("   - זמן סריקת אתרים: %.1f שניות", scraping_duration)
    LOGGER.info(
        "   - זמן ניתוח (AI) ושמירה לתור: %.1f שניות", analysis_duration
    )
    LOGGER.info("   - סך הכל זמן ריצה: %.1f שניות", total_duration)

if __name__ == "__main__":
    heartbeat_notifier: TelegramNotifier | None = None
    try:
        heartbeat_notifier = TelegramNotifier.from_environment()
    except ValueError as error:
        LOGGER.warning("Operational notifications disabled: %s", error)

    try:
        run_scraper(heartbeat_notifier=heartbeat_notifier)
    finally:
        if heartbeat_notifier is not None:
            heartbeat_notifier.close()
