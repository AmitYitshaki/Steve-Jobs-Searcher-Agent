"""Resilient Playwright scraping and public API discovery utilities."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import time
from contextlib import AbstractContextManager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import (
    parse_qsl,
    unquote,
    urlencode,
    urljoin,
    urlsplit,
    urlunsplit,
)

from bs4 import BeautifulSoup
from playwright.sync_api import (
    Page,
    Playwright,
    Response,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)
from playwright_stealth import Stealth

from models.job import JobRecord
from models.results import ScrapeResult, ScrapeStatus
from paths import ARTIFACTS_DIR, LOGS_DIR

LOGGER = logging.getLogger(__name__)

REALISTIC_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/152.0.0.0 Safari/537.36"
)
REALISTIC_VIEWPORT = {"width": 1440, "height": 900}
_STEALTH = Stealth(
    navigator_user_agent_override=REALISTIC_USER_AGENT,
)


def stealth_sync(page: Page) -> None:
    """Apply the current playwright-stealth API to one synchronous page."""

    _STEALTH.apply_stealth_sync(page)


CompanyConfig = Mapping[str, Any]
PlaywrightFactory = Callable[[], AbstractContextManager[Playwright]]


@dataclass(frozen=True)
class ApiDiscoveryRecord:
    """Describe a network response that may expose a public jobs API."""

    company_id: str
    url: str
    method: str
    status: int
    content_type: str
    resource_type: str
    discovered_at: str


class WafChallengeDetector:
    """Identify known WAF and JavaScript challenge responses."""

    SPARSE_TEXT_THRESHOLD = 200
    SPARSE_ANCHOR_THRESHOLD = 2
    KNOWN_MARKERS = (
        "kramericaindustries.ac_v2.lib.js",
        "window.rbzns",
        "winsocks();",
        "/cdn-cgi/challenge-platform/",
        "cf-chl-",
    )
    CHALLENGE_TEXT = (
        "checking your browser",
        "verify you are human",
        "enable javascript and cookies",
        "attention required",
        "access denied",
    )
    CHALLENGE_STATUSES = frozenset({401, 403, 429, 503})

    def detect_reason(
        self,
        html: str,
        status_code: int | None = None,
    ) -> str | None:
        """Return a human-readable challenge reason, or ``None``."""

        normalized_html = html.casefold()
        body_text = self._extract_body_text(html)
        anchor_count = self._count_anchors(html)
        is_sparse = (
            len(body_text) < self.SPARSE_TEXT_THRESHOLD
            and anchor_count < self.SPARSE_ANCHOR_THRESHOLD
        )
        challenge_status = status_code in self.CHALLENGE_STATUSES
        contains_challenge_text = any(
            marker in body_text for marker in self.CHALLENGE_TEXT
        )
        detected_marker = next(
            (
                marker
                for marker in self.KNOWN_MARKERS
                if marker.casefold() in normalized_html
            ),
            None,
        )

        if detected_marker and (
            is_sparse or challenge_status or contains_challenge_text
        ):
            return f"Known WAF marker detected: {detected_marker}"

        if contains_challenge_text and (is_sparse or challenge_status):
            return "Browser challenge text detected in the response body"

        if challenge_status and is_sparse:
            return f"HTTP {status_code} returned with sparse response content"

        return None

    @staticmethod
    def _extract_body_text(html: str) -> str:
        """Extract normalized visible body text without script contents."""

        soup = BeautifulSoup(html or "", "html.parser")
        if soup.body is None:
            return ""
        for element in soup.body.find_all(["script", "style", "noscript"]):
            element.decompose()
        return " ".join(soup.body.stripped_strings).casefold()

    @staticmethod
    def _count_anchors(html: str) -> int:
        """Count navigable anchors as a second meaningful-content signal."""

        soup = BeautifulSoup(html or "", "html.parser")
        return len(soup.find_all("a", href=True))


class NetworkResponseCollector:
    """Persist likely public job API endpoints observed by Playwright."""

    REPLACE_ATTEMPTS = 5
    REPLACE_RETRY_DELAY_SECONDS = 0.1
    API_KEYWORDS = ("job", "career", "search", "position")
    API_RESOURCE_TYPES = frozenset({"xhr", "fetch"})
    STATIC_RESOURCE_TYPES = frozenset(
        {"font", "image", "media", "stylesheet"}
    )
    IGNORED_HOST_FRAGMENTS = (
        "analytics.google",
        "google-analytics.com",
        "googlesyndication.com",
        "doubleclick.net",
        "cookielaw.org",
        "onetrust.com",
        "acsbapp.com",
        "clarity.ms",
        "facebook.com",
    )
    SENSITIVE_QUERY_KEYS = frozenset(
        {
            "access_token",
            "api_key",
            "apikey",
            "auth",
            "authorization",
            "code",
            "key",
            "session",
            "sessionid",
            "sig",
            "signature",
            "token",
        }
    )
    _log_lock = threading.Lock()

    def __init__(self, company_id: str, log_path: Path | str) -> None:
        """Initialize a collector for one company and discovery log."""

        self.company_id = company_id
        self.log_path = Path(log_path)
        self._seen: set[tuple[str, str]] = set()

    def attach(self, page: Page) -> None:
        """Subscribe to all browser response events on ``page``."""

        page.on("response", self.handle_response)

    def handle_response(self, response: Response) -> None:
        """Persist ``response`` when it resembles a public jobs endpoint."""

        try:
            request = response.request
            url = response.url
            method = request.method.upper()
            resource_type = request.resource_type.casefold()
            content_type = response.headers.get("content-type", "")

            if not self._is_candidate(url, content_type, resource_type):
                return

            sanitized_url = self._sanitize_url(url)
            candidate_key = (method, sanitized_url)
            if candidate_key in self._seen:
                return
            self._seen.add(candidate_key)

            record = ApiDiscoveryRecord(
                company_id=self.company_id,
                url=sanitized_url,
                method=method,
                status=response.status,
                content_type=content_type,
                resource_type=resource_type,
                discovered_at=datetime.now(timezone.utc).isoformat(),
            )
            self._append_record(record)
        except Exception:
            LOGGER.exception(
                "Could not record an API candidate for %s",
                self.company_id,
            )

    def _is_candidate(
        self,
        url: str,
        content_type: str,
        resource_type: str,
    ) -> bool:
        """Return whether response metadata resembles a jobs API."""

        url_parts = urlsplit(url)
        host = url_parts.netloc.casefold()
        if any(fragment in host for fragment in self.IGNORED_HOST_FRAGMENTS):
            return False

        is_json_api_call = (
            resource_type in self.API_RESOURCE_TYPES
            and "json" in content_type.casefold()
        )
        path_and_query = f"{url_parts.path}?{url_parts.query}".casefold()
        has_api_keyword = (
            resource_type not in self.STATIC_RESOURCE_TYPES
            and any(
                keyword in path_and_query for keyword in self.API_KEYWORDS
            )
        )
        return is_json_api_call or has_api_keyword

    def _append_record(self, record: ApiDiscoveryRecord) -> None:
        """Atomically append one discovery record to the JSON log."""

        with self._log_lock:
            records = self._load_records()
            record_data = asdict(record)
            identity = (
                record_data["company_id"],
                record_data["method"],
                record_data["url"],
            )
            if any(
                (
                    item.get("company_id"),
                    item.get("method"),
                    item.get("url"),
                )
                == identity
                for item in records
            ):
                return

            records.append(record_data)
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path = self.log_path.with_suffix(
                f"{self.log_path.suffix}.tmp"
            )
            with temporary_path.open("w", encoding="utf-8") as log_file:
                json.dump(records, log_file, ensure_ascii=False, indent=2)
            self._replace_with_retry(temporary_path)

    def _replace_with_retry(self, temporary_path: Path) -> None:
        """Retry transient Windows file locks during atomic replacement."""

        for attempt in range(1, self.REPLACE_ATTEMPTS + 1):
            try:
                os.replace(temporary_path, self.log_path)
                return
            except OSError as error:
                is_windows_lock = (
                    isinstance(error, PermissionError)
                    or getattr(error, "winerror", None) == 5
                )
                if not is_windows_lock or attempt >= self.REPLACE_ATTEMPTS:
                    raise
                time.sleep(self.REPLACE_RETRY_DELAY_SECONDS)

    def _load_records(self) -> list[dict[str, Any]]:
        """Read existing discovery entries, tolerating missing files."""

        if not self.log_path.exists():
            return []
        try:
            with self.log_path.open("r", encoding="utf-8") as log_file:
                data = json.load(log_file)
        except (OSError, json.JSONDecodeError):
            LOGGER.warning(
                "Ignoring unreadable API discovery log at %s",
                self.log_path,
            )
            return []
        if not isinstance(data, list):
            LOGGER.warning(
                "Ignoring non-list API discovery log at %s",
                self.log_path,
            )
            return []

        records = []
        for item in data:
            if not isinstance(item, dict):
                continue
            if self._is_candidate(
                url=str(item.get("url", "")),
                content_type=str(item.get("content_type", "")),
                resource_type=str(item.get("resource_type", "")),
            ):
                records.append(item)
        return records

    def _sanitize_url(self, url: str) -> str:
        """Redact secret-looking query values while preserving the endpoint."""

        parts = urlsplit(url)
        sanitized_query = []
        for key, value in parse_qsl(parts.query, keep_blank_values=True):
            if key.casefold() in self.SENSITIVE_QUERY_KEYS:
                sanitized_query.append((key, "[REDACTED]"))
            else:
                sanitized_query.append((key, value))
        return urlunsplit(
            (
                parts.scheme,
                parts.netloc,
                parts.path,
                urlencode(sanitized_query, doseq=True),
                parts.fragment,
            )
        )


class PlaywrightJobScraper:
    """Scrape job links while exposing WAF and API discovery outcomes."""

    JOB_LINK_KEYWORDS = ("job", "career", "req", "position", "role", "detail")
    TITLE_HEADING_NAMES = ("h1", "h2", "h3", "h4", "h5", "h6")
    TITLE_HEADING_SELECTOR = (
        "h1, h2, h3, h4, h5, h6, [fs-list-field='itemTitle']"
    )
    EXCLUDED_PATH_SEGMENTS = frozenset({
        "blog",
        "article",
        "story",
        "podcast",
        "meet-our-team",
    })
    SELECTOR_TIMEOUT_MS = 10_000
    SENSITIVE_HTML_PATTERN = re.compile(
        r"(?i)([?&](?:access_token|api_key|apikey|auth|authorization|"
        r"code|key|session|sessionid|sig|signature|token)=)"
        r"([^&\"'\s<>]+)"
    )

    def __init__(
        self,
        debug_dir: Path | str = ARTIFACTS_DIR,
        detector: WafChallengeDetector | None = None,
        playwright_factory: PlaywrightFactory = sync_playwright,
        navigation_timeout_ms: int = 30_000,
        content_timeout_ms: int = 10_000,
        settle_time_ms: int = 1_000,
    ) -> None:
        """Configure diagnostics, dependencies, and bounded wait times."""

        self.debug_dir = Path(debug_dir)
        self.detector = detector or WafChallengeDetector()
        self.playwright_factory = playwright_factory
        self.navigation_timeout_ms = navigation_timeout_ms
        self.content_timeout_ms = content_timeout_ms
        self.settle_time_ms = settle_time_ms

    def scrape(self, company: CompanyConfig) -> ScrapeResult:
        """Scrape one company and return jobs with a structured status."""

        company_id = str(company.get("company_id", "")).strip()
        url = str(company.get("api_url", "")).strip()
        configured_selector = company.get("job_selector")
        job_selector = (
            configured_selector.strip()
            if isinstance(configured_selector, str)
            else ""
        )
        configured_selector_timeout = company.get(
            "selector_timeout_ms",
            self.SELECTOR_TIMEOUT_MS,
        )
        selector_timeout_ms = self.SELECTOR_TIMEOUT_MS
        if (
            isinstance(configured_selector_timeout, int)
            and not isinstance(configured_selector_timeout, bool)
            and configured_selector_timeout > 0
        ):
            selector_timeout_ms = configured_selector_timeout
        elif "selector_timeout_ms" in company:
            LOGGER.warning(
                "Invalid selector_timeout_ms for %s; using %s",
                company_id,
                self.SELECTOR_TIMEOUT_MS,
            )
        if not company_id or not url:
            return ScrapeResult(
                status=ScrapeStatus.FAILED,
                jobs=[],
                message="company_id and api_url are required",
            )

        diagnostic_paths: tuple[str, ...] = ()

        try:
            self.debug_dir.mkdir(parents=True, exist_ok=True)
            with self.playwright_factory() as playwright:
                return self._scrape_with_browser(
                    playwright=playwright,
                    company_id=company_id,
                    url=url,
                    job_selector=job_selector,
                    selector_timeout_ms=selector_timeout_ms,
                )
        except Exception as error:
            return ScrapeResult(
                status=ScrapeStatus.FAILED,
                jobs=[],
                message=f"{type(error).__name__}: {error}",
                diagnostic_paths=diagnostic_paths,
            )

    def _scrape_with_browser(
        self,
        playwright: Playwright,
        company_id: str,
        url: str,
        job_selector: str = "",
        selector_timeout_ms: int = SELECTOR_TIMEOUT_MS,
    ) -> ScrapeResult:
        """Run one browser session and close all resources before returning."""

        browser: Any = None
        context: Any = None
        page: Any = None
        html = ""
        status_code: int | None = None
        waf_reason: str | None = None
        diagnostic_paths: tuple[str, ...] = ()

        try:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=REALISTIC_USER_AGENT,
                viewport=REALISTIC_VIEWPORT,
                timezone_id="Asia/Jerusalem",
                locale="en-US",
            )
            page = context.new_page()
            stealth_sync(page)
            collector = NetworkResponseCollector(
                company_id=company_id,
                log_path=LOGS_DIR / "api_discovery_log.json",
            )
            collector.attach(page)

            navigation_response = page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=self.navigation_timeout_ms,
            )
            self._wait_for_meaningful_content(page)
            html = page.content()
            status_code = (
                navigation_response.status
                if navigation_response is not None
                else None
            )
            waf_reason = self.detector.detect_reason(html, status_code)

            if waf_reason:
                diagnostic_paths = self._write_diagnostics(
                    page=page,
                    company_id=company_id,
                    html=html,
                    status_code=status_code,
                    waf_reason=waf_reason,
                )
                return ScrapeResult(
                    status=ScrapeStatus.WAF_BLOCKED,
                    jobs=[],
                    message=waf_reason,
                    diagnostic_paths=diagnostic_paths,
                )

            if job_selector:
                self._wait_for_job_selector(
                    page,
                    job_selector,
                    selector_timeout_ms,
                )
                html = page.content()
                jobs = self._extract_jobs_by_selector(
                    page=page,
                    selector=job_selector,
                    base_url=url,
                    company_id=company_id,
                )
                LOGGER.info(
                    "Extracted %s jobs for %s with selector %r",
                    len(jobs),
                    company_id,
                    job_selector,
                )
            else:
                jobs = self._extract_jobs(html, url, company_id)
            if not jobs:
                diagnostic_paths = self._write_diagnostics(
                    page=page,
                    company_id=company_id,
                    html=html,
                    status_code=status_code,
                    waf_reason=None,
                )
                extraction_method = (
                    f"configured selector {job_selector!r}"
                    if job_selector
                    else "universal rules"
                )
                return ScrapeResult(
                    status=ScrapeStatus.NO_JOBS,
                    jobs=[],
                    message=f"No job links matched {extraction_method}",
                    diagnostic_paths=diagnostic_paths,
                )

            return ScrapeResult(
                status=ScrapeStatus.SUCCESS,
                jobs=jobs,
                diagnostic_paths=diagnostic_paths,
            )
        except Exception as error:
            if page is not None:
                try:
                    if not html:
                        html = page.content()
                    diagnostic_paths = self._write_diagnostics(
                        page=page,
                        company_id=company_id,
                        html=html,
                        status_code=status_code,
                        waf_reason=waf_reason,
                    )
                except Exception as diagnostic_error:
                    LOGGER.warning(
                        "Could not write failure diagnostics for %s: %s",
                        company_id,
                        diagnostic_error,
                    )
            return ScrapeResult(
                status=ScrapeStatus.FAILED,
                jobs=[],
                message=f"{type(error).__name__}: {error}",
                diagnostic_paths=diagnostic_paths,
            )
        finally:
            if context is not None:
                try:
                    context.close()
                except Exception:
                    LOGGER.exception("Could not close browser context")
            if browser is not None:
                try:
                    browser.close()
                except Exception:
                    LOGGER.exception("Could not close browser")

    def _wait_for_meaningful_content(self, page: Page) -> None:
        """Wait for text or links, then briefly observe late API responses."""

        try:
            page.wait_for_function(
                """
                () => document.body && (
                    document.body.innerText.trim().length > 0 ||
                    document.querySelectorAll('a[href]').length > 0
                )
                """,
                timeout=self.content_timeout_ms,
            )
        except PlaywrightTimeoutError:
            LOGGER.info("Timed out waiting for meaningful page content")

        if self.settle_time_ms > 0:
            page.wait_for_timeout(self.settle_time_ms)

    def _wait_for_job_selector(
        self,
        page: Page,
        selector: str,
        timeout_ms: int = SELECTOR_TIMEOUT_MS,
    ) -> None:
        """Wait for SPA job elements while tolerating a bounded timeout."""

        try:
            page.wait_for_selector(
                selector,
                state="visible",
                timeout=timeout_ms,
            )
        except PlaywrightTimeoutError:
            LOGGER.warning("Selector %s not found in time", selector)

    def _write_diagnostics(
        self,
        page: Page,
        company_id: str,
        html: str,
        status_code: int | None,
        waf_reason: str | None,
    ) -> tuple[str, ...]:
        """Write sanitized HTML, screenshot, and navigation metadata."""

        html_path = self.debug_dir / f"{company_id}.html"
        screenshot_path = self.debug_dir / f"{company_id}.png"
        metadata_path = self.debug_dir / f"{company_id}_diagnostic.json"
        written_paths: list[str] = []

        sanitized_html = self.SENSITIVE_HTML_PATTERN.sub(
            r"\1[REDACTED]",
            html,
        )
        html_path.write_text(sanitized_html, encoding="utf-8")
        written_paths.append(str(html_path))
        try:
            page.screenshot(
                path=str(screenshot_path),
                timeout=5000,
            )
            written_paths.append(str(screenshot_path))
        except Exception as error:
            LOGGER.warning(
                "Could not capture screenshot for %s: %s",
                company_id,
                error,
            )

        with metadata_path.open("w", encoding="utf-8") as metadata_file:
            json.dump(
                {
                    "company_id": company_id,
                    "navigation_status": status_code,
                    "waf_detected": waf_reason is not None,
                    "waf_reason": waf_reason,
                    "captured_at": datetime.now(timezone.utc).isoformat(),
                },
                metadata_file,
                ensure_ascii=False,
                indent=2,
            )
        written_paths.append(str(metadata_path))

        return tuple(written_paths)

    @staticmethod
    def _first_text_line(raw_title: str) -> str:
        """Return the first non-empty line from extracted anchor text."""

        return next(
            (line.strip() for line in raw_title.splitlines() if line.strip()),
            "",
        )

    @staticmethod
    def _element_href(element: Any) -> str:
        """Return an element's href or the first descendant anchor href."""

        href = element.get_attribute("href")
        if isinstance(href, str) and href.strip():
            return href.strip()

        descendant_anchor = element.locator("a[href]").first
        if descendant_anchor.count() == 0:
            return ""
        descendant_href = descendant_anchor.get_attribute("href")
        if not isinstance(descendant_href, str):
            return ""
        return descendant_href.strip()

    def _extract_jobs_by_selector(
        self,
        page: Page,
        selector: str,
        base_url: str,
        company_id: str,
    ) -> list[JobRecord]:
        """Extract links from a configured CSS selector without heuristics."""

        jobs: list[JobRecord] = []
        seen_urls: set[str] = set()
        elements = page.locator(selector).all()

        for element in elements:
            try:
                href = self._element_href(element)
                raw_card_text = element.inner_text()
                heading = element.locator(self.TITLE_HEADING_SELECTOR).first
                if heading.count() > 0:
                    raw_title = heading.inner_text()
                    title_source = "heading"
                else:
                    raw_title = raw_card_text
                    title_source = "fallback"
            except Exception as error:
                LOGGER.debug(
                    "Skipping failed element for selector %s: %s",
                    selector,
                    error,
                )
                continue
            if not href:
                continue
            title = (
                self._first_text_line(raw_title)
                if isinstance(raw_title, str)
                else ""
            )
            if not title:
                continue

            full_url = urljoin(base_url, href)
            if full_url in seen_urls:
                continue
            seen_urls.add(full_url)
            LOGGER.debug(
                "Extracted title for %s using %s path",
                company_id,
                title_source,
            )

            stable_id = hashlib.sha256(
                full_url.encode("utf-8")
            ).hexdigest()[:16]
            jobs.append(
                {
                    "id": f"{company_id}_{stable_id}",
                    "title": title,
                    "location": (
                        raw_card_text.strip()
                        if isinstance(raw_card_text, str)
                        else ""
                    ),
                    "url": full_url,
                    "content": "",
                }
            )

        return jobs

    def _extract_jobs(
        self,
        html: str,
        base_url: str,
        company_id: str,
    ) -> list[JobRecord]:
        """Extract unique job-like anchors from rendered HTML."""

        soup = BeautifulSoup(html, "lxml")
        jobs: list[JobRecord] = []
        seen_urls: set[str] = set()

        for anchor in soup.find_all("a", href=True):
            href = str(anchor["href"]).strip()
            raw_card_text = anchor.get_text(" ", strip=True)
            heading = anchor.find(self.TITLE_HEADING_NAMES)
            if heading is not None:
                raw_title = heading.get_text(" ", strip=True)
                title_source = "heading"
            else:
                raw_title = anchor.get_text("\n", strip=True)
                title_source = "fallback"
            title = self._first_text_line(raw_title)
            full_url = urljoin(base_url, href)

            if len(title) <= 5:
                continue
            url_path = unquote(urlsplit(full_url).path).casefold()
            path_segments = {
                segment
                for segment in url_path.split("/")
                if segment
            }
            if not self.EXCLUDED_PATH_SEGMENTS.isdisjoint(path_segments):
                continue
            if not any(
                keyword in url_path
                for keyword in self.JOB_LINK_KEYWORDS
            ):
                continue
            if full_url in seen_urls:
                continue
            seen_urls.add(full_url)
            LOGGER.debug(
                "Extracted title for %s using %s path",
                company_id,
                title_source,
            )

            stable_id = hashlib.sha256(full_url.encode("utf-8")).hexdigest()[:16]
            jobs.append(
                {
                    "id": f"{company_id}_{stable_id}",
                    "title": title,
                    "location": raw_card_text,
                    "url": full_url,
                    "content": "",
                }
            )

        return jobs
