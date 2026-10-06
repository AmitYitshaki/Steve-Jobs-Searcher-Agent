import html
import json
import logging
import os
import re
import time
import unicodedata
from dataclasses import dataclass
from typing import Any, Callable, Container, Mapping, Protocol, Sequence

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

# Load environment variables from .env.
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

# Blacklist: reject these titles even when they contain student keywords.
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
    "engineer i",
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
    "security engineer", "security researcher", "application security",
    "penetration tester", "soc analyst", "security analyst",
    "cyber security engineer", "cybersecurity engineer", "threat researcher",
    "threat analyst", "incident response", "incident responder",
    "security operations", "malware researcher", "vulnerability researcher",
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
    """Lower-case and strip punctuation so phrases match whole words only."""

    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text).lower()
    text = re.sub(r"[-_/]+", " ", text)
    text = re.sub(r"[^\w֐-׿\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def contains_phrase(text: str, phrase: str) -> bool:
    """Return whether ``phrase`` appears in ``text`` as a whole phrase."""

    normalized_text = normalize_text(text)
    normalized_phrase = normalize_text(phrase)
    pattern = rf"(?<!\w){re.escape(normalized_phrase)}(?!\w)"
    return re.search(pattern, normalized_text) is not None


class TitleRelevanceFilter:
    """Decide from a job title alone whether it is an entry-level tech role.

    Rules, in order: an exclusion keyword (senior, manager, sales, ...) blocks
    the title unless it is part of the matched target-role phrase; a strong
    entry-level signal (student, intern) admits it; a weak signal (junior,
    graduate) admits it only together with a target-role keyword.
    """

    def __init__(
        self,
        exclude_keywords: Sequence[str] = tuple(EXCLUDE_KEYWORDS),
        strong_keywords: Sequence[str] = tuple(
            STRONG_ENTRY_LEVEL_KEYWORDS + HEBREW_ENTRY_LEVEL_KEYWORDS
        ),
        weak_keywords: Sequence[str] = tuple(WEAK_ENTRY_LEVEL_KEYWORDS),
        role_keywords: Sequence[str] = tuple(
            TARGET_ROLE_KEYWORDS + HEBREW_ROLE_KEYWORDS
        ),
    ) -> None:
        """Store the keyword tiers; defaults are the module-level lists."""

        self._exclude_keywords = tuple(exclude_keywords)
        self._strong_keywords = tuple(strong_keywords)
        self._weak_keywords = tuple(weak_keywords)
        self._role_keywords = tuple(role_keywords)

    @staticmethod
    def _first_match(title: str, keywords: Sequence[str]) -> str | None:
        """Return the first complete keyword phrase found in ``title``."""

        return next(
            (keyword for keyword in keywords if contains_phrase(title, keyword)),
            None,
        )

    @staticmethod
    def _all_matches(title: str, keywords: Sequence[str]) -> list[str]:
        """Return every complete keyword phrase found in ``title``."""

        return [
            keyword for keyword in keywords if contains_phrase(title, keyword)
        ]

    def target_role_keyword(self, title: str) -> str | None:
        """Return the first configured software-adjacent role in a title."""

        return self._first_match(title, self._role_keywords)

    def matches_target_role(self, title: str) -> bool:
        """Return whether a title proves catalog relevance, ignoring seniority.

        Company-discovery batches use this narrower predicate as an activation
        gate: an employer needs at least one current target-domain role, but
        that role does not itself need to be entry level. Candidate alert
        filtering remains the responsibility of :meth:`evaluate`.
        """

        return self.target_role_keyword(title) is not None

    def _blocking_exclusions(
        self,
        title: str,
        role_keyword: str | None,
    ) -> list[str]:
        """Return exclusions that are not merely part of a target role name.

        Exclusion keywords hold seniority and out-of-scope function words, but
        some of them appear inside role names we explicitly target: "manager"
        is a substring of "product manager intern", which the target list
        holds verbatim. Excluding on such a word contradicts our own target
        list, so an exclusion contained in the matched role phrase is
        discarded. Any exclusion outside that phrase ("senior", "sales")
        still blocks the title.
        """

        exclusions = self._all_matches(title, self._exclude_keywords)
        if role_keyword is None:
            return exclusions
        return [
            keyword
            for keyword in exclusions
            if not contains_phrase(role_keyword, keyword)
        ]

    def evaluate(self, title: str) -> TitleDecision:
        """Evaluate title relevance while preserving strong-signal recall."""

        role_keyword = self.target_role_keyword(title)
        blocking_exclusions = self._blocking_exclusions(title, role_keyword)
        if blocking_exclusions:
            return TitleDecision(
                allowed=False,
                reason="excluded title keyword",
                matched_keyword=blocking_exclusions[0],
            )

        strong_keyword = self._first_match(title, self._strong_keywords)
        if strong_keyword is not None:
            return TitleDecision(
                allowed=True,
                reason="strong entry-level signal",
                matched_keyword=strong_keyword,
            )

        weak_keyword = self._first_match(title, self._weak_keywords)
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


class CompanyRouter:
    """Route a configured company to the adapter that can fetch its jobs.

    Adapter tables and adapter functions are read from module scope on every
    call, so a test can patch any of them on ``scrapers.orchestrator``.
    """

    DIRECTLY_ROUTED_ATS_TYPES = frozenset({"successfactors", "eightfold"})

    def unroutable_company_ids(
        self,
        companies: Sequence[Mapping[str, Any]],
    ) -> list[str]:
        """Return active company IDs without a configured fetch route."""

        unroutable_company_ids: list[str] = []
        for company in companies:
            if not company.get("is_active", True):
                continue
            if not self._has_route(company):
                unroutable_company_ids.append(
                    str(company.get("company_id", "<missing>"))
                )
        return unroutable_company_ids

    def _has_route(self, company: Mapping[str, Any]) -> bool:
        """Mirror :meth:`fetch` to decide whether a company can be routed."""

        ats_type = company.get("ats_type")
        company_id = str(company.get("company_id", "<missing>"))
        fetch_strategy = company.get("fetch_strategy")
        has_custom_api_route = (
            ats_type == "custom"
            and fetch_strategy == "api"
            and company_id in CUSTOM_API_ADAPTERS
        )
        # Mirrors the ats_type-keyed branch in fetch(). Without it, every ATS
        # served by a shared custom adapter (oracle_recruiting_cloud today)
        # is reported unroutable on every run despite routing fine.
        has_custom_api_route_by_ats_type = (
            fetch_strategy == "api"
            and ats_type in CUSTOM_API_ADAPTERS_BY_ATS_TYPE
        )
        return (
            ats_type in ATS_FIELD_MAP
            or ats_type in self.DIRECTLY_ROUTED_ATS_TYPES
            or fetch_strategy == "browser"
            or has_custom_api_route
            or has_custom_api_route_by_ats_type
        )

    def fetch(self, company: Mapping[str, Any]) -> ScrapeResult:
        """Dispatch one company and always expose a typed scrape outcome."""

        ats_type = company.get("ats_type")
        api_url = company.get("api_url")
        company_id = company.get("company_id")
        fetch_strategy = company.get("fetch_strategy")

        LOGGER.info(
            "🔍 Scanning %s (ATS: %s)...", company.get("company_name"), ats_type
        )

        custom_api_adapter = CUSTOM_API_ADAPTERS.get(str(company_id))
        if (
            ats_type == "custom"
            and fetch_strategy == "api"
            and custom_api_adapter is not None
        ):
            return custom_api_adapter(company)

        custom_api_adapter_by_ats_type = CUSTOM_API_ADAPTERS_BY_ATS_TYPE.get(
            str(ats_type)
        )
        if fetch_strategy == "api" and custom_api_adapter_by_ats_type is not None:
            return custom_api_adapter_by_ats_type(company)

        custom_browser_adapter = CUSTOM_BROWSER_ADAPTERS.get(str(ats_type))
        if fetch_strategy == "browser" and custom_browser_adapter is not None:
            return custom_browser_adapter(company)

        if ats_type in ATS_FIELD_MAP:
            return fetch_ats_jobs(company, ATS_FIELD_MAP[ats_type])

        # SuccessFactors renders HTML rather than JSON.
        if ats_type == "successfactors":
            return scrape_successfactors(company)

        # Eightfold API, with a universal Playwright fallback inside.
        if ats_type == "eightfold":
            return scrape_eightfold(str(company_id), str(api_url))

        # Browser-configured career sites use the universal Playwright scraper.
        if fetch_strategy == "browser":
            return scrape_universal_playwright(company)

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


class OperationalReporter:
    """Send producer operational messages without ever failing the run.

    Covers the zero-job heartbeat and the scraper-health digest. Both go
    through an optional notifier; a missing notifier or a failed send is
    logged and ignored, so candidate-job processing is never affected.
    """

    def __init__(self, notifier: OperationalMessageSender | None) -> None:
        """Wrap an optional transport (``None`` disables all messages)."""

        self._notifier = notifier

    def send_heartbeat(self) -> None:
        """Notify operators that the cycle succeeded with zero new jobs."""

        self._send(HEARTBEAT_MESSAGE, "Heartbeat")

    def send_health_digest(
        self,
        previous_state: Mapping[str, Mapping[str, Any]],
        current_state: Mapping[str, Mapping[str, Any]],
    ) -> None:
        """Send one digest when scraper-health anomaly state changed."""

        message = self.build_health_digest(previous_state, current_state)
        if message is not None:
            self._send(message, "Scraper-health digest")

    def _send(self, message: str, message_kind: str) -> None:
        """Deliver one message, logging rather than raising on failure."""

        if self._notifier is None:
            return
        try:
            result = self._notifier.send(message)
        except Exception as error:
            LOGGER.warning(
                "%s delivery raised %s; the cycle still succeeded.",
                message_kind,
                type(error).__name__,
            )
            return
        if not getattr(result, "success", True):
            LOGGER.warning("%s delivery did not succeed.", message_kind)

    @staticmethod
    def build_health_digest(
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
            company_name = str(current.get("company_name") or company_id)
            if old_status == new_status:
                # A company that has never once succeeded stays "unverified"
                # forever regardless of current errors (see
                # CompanyHealthTracker), so it can never cross an
                # ANOMALY_HEALTH_STATUSES transition. Watch last_error_type
                # directly so a newly-blocked (or newly-recovered)
                # never-verified company still surfaces here.
                old_error = previous.get("last_error_type")
                new_error = current.get("last_error_type")
                if old_error == new_error:
                    continue
                if new_error:
                    lines.append(
                        f"🚨 {company_name}: error appeared ({new_error}), "
                        f"status={new_status}"
                    )
                else:
                    lines.append(
                        f"✅ {company_name}: error cleared "
                        f"({old_error} -> none), status={new_status}"
                    )
                continue
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
                lines.append(f"🚨 {company_name}: " + " | ".join(details))
            elif (
                old_status in ANOMALY_HEALTH_STATUSES
                and new_status == "healthy"
            ):
                lines.append(
                    f"✅ {company_name}: recovered ({old_status} -> healthy)"
                )

        if not lines:
            return None
        return "Scraper health changes:\n" + "\n".join(lines)


class TelegramAlertFormatter:
    """Render one candidate job and its LLM analysis as a Telegram alert."""

    @staticmethod
    def format(job: Mapping[str, Any], analysis: str) -> str:
        """Return Telegram HTML with escaped job fields and the analysis.

        The labels stay in Hebrew: this is the message the candidate reads.
        """

        def escape(value: Any) -> str:
            return html.escape(str(value), quote=False)

        return (
            f"🚨 <b>משרה חדשה נמצאה: {escape(job['title'])}</b> 🚨\n"
            f"🏢 חברה: {escape(job['company_name'])}\n"
            f"📍 מיקום: {escape(job['location'])}\n"
            f"🔗 קישור: {escape(job['job_url'])}\n\n"
            f"{analysis}"
        )


_TITLE_FILTER = TitleRelevanceFilter()
_ROUTER = CompanyRouter()


def matches_target_role(title: str) -> bool:
    """Module-level entry point for :meth:`TitleRelevanceFilter.matches_target_role`."""

    return _TITLE_FILTER.matches_target_role(title)


def is_relevant_job(title: str) -> TitleDecision:
    """Module-level entry point for :meth:`TitleRelevanceFilter.evaluate`."""

    return _TITLE_FILTER.evaluate(title)


def validate_company_routing(companies: list[dict]) -> list[str]:
    """Return active company IDs without a configured fetch route."""

    return _ROUTER.unroutable_company_ids(companies)


def fetch_jobs_from_company(company: Mapping[str, Any]) -> ScrapeResult:
    """Dispatch one company and always expose a typed scrape outcome."""

    return _ROUTER.fetch(company)


def load_json(filepath: str | os.PathLike[str]) -> Any:
    """Load a JSON file, returning an empty list when it does not exist."""

    if not os.path.exists(filepath):
        return []
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def is_in_location(
    job_location: str | None,
    location_filters: Sequence[str] | None,
) -> bool:
    """Return whether a job location contains any configured filter string."""

    if not location_filters:
        return True
    if not job_location:
        return False
    job_loc_lower = job_location.lower()
    return any(loc.lower() in job_loc_lower for loc in location_filters)


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


class JobProducer:
    """One producer cycle: scan companies, filter, dedupe, analyze, enqueue.

    It never contacts Telegram for candidate jobs; those only reach the
    durable queue. Fetching, analysis and config loading go through the
    module-level ``fetch_jobs_from_company``, ``analyze_job`` and
    ``load_json`` names so tests can patch them on ``scrapers.orchestrator``.
    """

    def __init__(
        self,
        queue: PendingAlertQueue,
        location_filter: LocationFilter,
        history_store: JobHistoryStore,
        health_store: ScraperHealthStore,
        reporter: OperationalReporter,
    ) -> None:
        """Inject every store and collaborator the cycle touches."""

        self._queue = queue
        self._location_filter = location_filter
        self._history_store = history_store
        self._health_store = health_store
        self._reporter = reporter

    def run(self) -> None:
        """Run one full cycle and log a timing report."""

        LOGGER.info("🚀 Starting job scan...")
        total_start_time = time.time()

        companies = load_json(CONFIG_DIR / "companies.json")
        unroutable_company_ids = validate_company_routing(companies)
        if unroutable_company_ids:
            LOGGER.error(
                "Unroutable active company configurations: %s",
                ", ".join(unroutable_company_ids),
            )
        if not companies:
            LOGGER.warning("⚠️ config/companies.json is empty.")
            return

        new_jobs = self._scan_companies(companies)
        scraping_end_time = time.time()

        self._analyze_and_enqueue(new_jobs)
        analysis_end_time = time.time()

        self._log_timings(total_start_time, scraping_end_time, analysis_end_time)

    def _scan_companies(
        self,
        companies: Sequence[Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        """Phase 1: fetch every active company and collect new relevant jobs."""

        history = self._history_store.load()
        health_state = self._health_store.load()
        new_health_state = dict(health_state)
        pending_ids = self._queue.ids()
        new_jobs: list[dict[str, Any]] = []
        queued_job_ids: set[str] = set()

        for company in companies:
            if not company.get("is_active", True):
                continue

            company_id = str(company.get("company_id", "<missing>"))
            tracker = CompanyHealthTracker(
                company_id=company_id,
                company_name=str(company.get("company_name", company_id)),
                previous_state=health_state.get(company_id, {}),
            )
            try:
                self._scan_company(
                    company,
                    tracker,
                    seen_ids=(history, pending_ids, queued_job_ids),
                    new_jobs=new_jobs,
                )
            except Exception as error:
                tracker.record_failure(error)
                LOGGER.exception("Company scrape failed for %s.", company_id)
            finally:
                new_health_state[company_id] = tracker.snapshot()
                LOGGER.info("%s", tracker.summary_line())

        self._health_store.save(new_health_state)
        self._reporter.send_health_digest(health_state, new_health_state)
        return new_jobs

    def _scan_company(
        self,
        company: Mapping[str, Any],
        tracker: CompanyHealthTracker,
        seen_ids: tuple[Container[str], Container[str], set[str]],
        new_jobs: list[dict[str, Any]],
    ) -> None:
        """Fetch one company and append its new, relevant jobs to ``new_jobs``.

        ``seen_ids`` is (delivered history, pending queue, queued this scan);
        a job found in any of them is a duplicate. The third set is updated.
        """

        company_id = str(company.get("company_id", "<missing>"))
        company_name = str(company.get("company_name", company_id))
        history, pending_ids, queued_job_ids = seen_ids

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
            return

        jobs = scrape_result.jobs
        tracker.record_fetch(len(jobs))
        location_filters = company.get("location_filters", [])

        for job in jobs:
            job_url = self._accepted_job_url(
                company, job, location_filters, tracker
            )
            if job_url is None:
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
            new_jobs.append({
                **job,
                "company_name": company_name,
                "job_url": job_url,
            })
            queued_job_ids.add(job["id"])

    def _accepted_job_url(
        self,
        company: Mapping[str, Any],
        job: Mapping[str, Any],
        location_filters: Sequence[str],
        tracker: CompanyHealthTracker,
    ) -> str | None:
        """Apply title and location rules; return the job URL if accepted.

        Returns ``None`` (after recording the rejection) when the job fails
        the title filter, the foreign-location filter, or both location
        checks together.
        """

        title_decision = is_relevant_job(job["title"])
        if not title_decision.allowed:
            tracker.record_title_rejection()
            match_details = ""
            if title_decision.matched_keyword is not None:
                match_details = f" '{title_decision.matched_keyword}'"
            LOGGER.debug(
                "Rejecting %s: title %s%s.",
                job["id"],
                title_decision.reason,
                match_details,
            )
            return None

        job_url = extract_job_url(job) or str(company.get("api_url", ""))
        location_decision = self._location_filter.evaluate(
            job_title=job["title"],
            job_url=job_url,
            job_location=job["location"],
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
            return None

        # A job passes if either the configured substring filters or the
        # LocationFilter's Israeli-city recognition accepts its location.
        location_match = is_in_location(job["location"], location_filters)
        recognized_israeli_location = (
            location_decision.source == "location"
            and location_decision.matched_location is not None
        )
        if not location_match and not recognized_israeli_location:
            tracker.record_location_rejection()
            LOGGER.debug(
                "Rejecting %s: adapter location %r does not match "
                "configured filters %r.",
                job["id"],
                job["location"],
                location_filters,
            )
            return None

        return job_url

    def _analyze_and_enqueue(self, new_jobs: Sequence[Mapping[str, Any]]) -> None:
        """Phase 2: analyze each new job with the LLM and queue its alert."""

        if not new_jobs:
            LOGGER.info("😴 No new relevant jobs found this time.")
            self._reporter.send_heartbeat()
            return

        LOGGER.info(
            "✅ Found %s new relevant jobs. Sending to Steve for analysis...",
            len(new_jobs),
        )
        for job in new_jobs:
            LOGGER.info("🤖 Analyzing: %s in %s", job["title"], job["location"])

            try:
                analysis = analyze_job(
                    job_title=job["title"],
                    job_location=job["location"],
                    job_content=job.get("content", ""),
                )
            except Exception as error:
                LOGGER.error(
                    "❌ Job analysis failed; the job will not be queued: %s",
                    type(error).__name__,
                )
                continue

            alert = PendingAlert(
                job_id=job["id"],
                company_name=job["company_name"],
                job_url=job["job_url"],
                llm_summary=TelegramAlertFormatter.format(job, analysis),
            )
            if self._queue.append(alert):
                LOGGER.info("✅ Job %s added to the alert queue.", job["id"])
            else:
                LOGGER.info("ℹ️ Job %s is already queued.", job["id"])
            LOGGER.info("-" * 40)

    @staticmethod
    def _log_timings(
        total_start_time: float,
        scraping_end_time: float,
        analysis_end_time: float,
    ) -> None:
        """Log how long scanning, analysis and the whole cycle took."""

        LOGGER.info("🏁 Scan complete.")
        LOGGER.info("⏱️ Performance report:")
        LOGGER.info(
            "   - Site scanning time: %.1f s",
            scraping_end_time - total_start_time,
        )
        LOGGER.info(
            "   - AI analysis and queueing time: %.1f s",
            analysis_end_time - scraping_end_time,
        )
        LOGGER.info(
            "   - Total run time: %.1f s",
            analysis_end_time - total_start_time,
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

    JobProducer(
        queue=queue or PendingAlertQueue(PENDING_ALERTS_FILE),
        location_filter=location_filter or LocationFilter(strict_mode=False),
        history_store=history_store or JobHistoryStore(HISTORY_FILE),
        health_store=health_store or ScraperHealthStore(HEALTH_FILE),
        reporter=OperationalReporter(heartbeat_notifier),
    ).run()


def main() -> None:
    """Run one producer cycle with Telegram operational messages if configured."""

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


if __name__ == "__main__":
    main()
