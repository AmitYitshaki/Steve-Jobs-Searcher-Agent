"""Deterministic tests for resilient Playwright scraping components."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import (
    Response,
    TimeoutError as PlaywrightTimeoutError,
)

from models.results import ScrapeResult, ScrapeStatus
from scrapers.browser.custom_adapters import scrape_universal_playwright
from scrapers.browser.playwright_driver import (
    ApiDiscoveryRecord,
    NetworkResponseCollector,
    PlaywrightJobScraper,
    REALISTIC_USER_AGENT,
    REALISTIC_VIEWPORT,
    WafChallengeDetector,
)


class WafChallengeDetectorTests(unittest.TestCase):
    """Verify known challenges are distinct from legitimate empty pages."""

    def test_detects_rafael_challenge_marker(self) -> None:
        """Recognize the JavaScript marker observed on Rafael."""

        html = (
            "<html><head><script "
            'src="/kramericaindustries.ac_v2.lib.js"></script></head>'
            "<body></body></html>"
        )

        reason = WafChallengeDetector().detect_reason(html, 200)

        self.assertIn("kramericaindustries", reason or "")

    def test_detects_empty_challenge_status(self) -> None:
        """Recognize an empty response returned with a challenge status."""

        reason = WafChallengeDetector().detect_reason(
            "<html><body></body></html>",
            403,
        )

        self.assertEqual(
            reason,
            "HTTP 403 returned with sparse response content",
        )

    def test_does_not_flag_legitimate_empty_page(self) -> None:
        """Avoid treating every empty successful page as a WAF block."""

        reason = WafChallengeDetector().detect_reason(
            "<html><body></body></html>",
            200,
        )

        self.assertIsNone(reason)

    def test_does_not_flag_cloudflare_script_with_healthy_job_dom(
        self,
    ) -> None:
        """Treat passive Cloudflare scripts as healthy when jobs loaded."""

        html = (
            "<html><head><script "
            'src="/cdn-cgi/challenge-platform/scripts/jsd/main.js">'
            "</script></head><body>"
            f"<p>{'Healthy careers content. ' * 20}</p>"
            '<a href="/jobs/123">Student Software Engineer</a>'
            '<a href="/jobs/456">Junior Data Analyst</a>'
            "</body></html>"
        )

        reason = WafChallengeDetector().detect_reason(html, 200)

        self.assertIsNone(reason)


class NetworkResponseCollectorTests(unittest.TestCase):
    """Verify API candidates are selected, sanitized, and persisted."""

    def test_attach_subscribes_response_handler(self) -> None:
        """Automatically inspect every response emitted by the page."""

        page = MagicMock()
        collector = NetworkResponseCollector(
            "example",
            "logs/api_discovery_log.json",
        )

        collector.attach(page)

        page.on.assert_called_once_with("response", collector.handle_response)

    def test_logs_json_xhr_with_method_and_sanitized_url(self) -> None:
        """Persist JSON XHR metadata and redact secret query values."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            log_path = Path(temporary_directory) / "api_discovery_log.json"
            collector = NetworkResponseCollector("rafael", log_path)
            response = cast(
                Response,
                SimpleNamespace(
                    url=(
                        "https://example.test/api/list?"
                        "token=secret&location=Israel"
                    ),
                    status=200,
                    headers={"content-type": "application/json; charset=utf-8"},
                    request=SimpleNamespace(
                        method="post",
                        resource_type="xhr",
                    ),
                ),
            )

            collector.handle_response(response)

            records = json.loads(log_path.read_text(encoding="utf-8"))
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["company_id"], "rafael")
            self.assertEqual(records[0]["method"], "POST")
            self.assertEqual(records[0]["status"], 200)
            query = parse_qs(urlsplit(records[0]["url"]).query)
            self.assertEqual(query["token"], ["[REDACTED]"])
            self.assertEqual(query["location"], ["Israel"])

    def test_logs_keyword_url_without_json_content_type(self) -> None:
        """Persist a non-static URL containing a jobs keyword."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            log_path = Path(temporary_directory) / "api_discovery_log.json"
            collector = NetworkResponseCollector("example", log_path)
            response = cast(
                Response,
                SimpleNamespace(
                    url="https://example.test/careers/search",
                    status=200,
                    headers={"content-type": "text/html"},
                    request=SimpleNamespace(
                        method="get",
                        resource_type="document",
                    ),
                ),
            )

            collector.handle_response(response)

            records = json.loads(log_path.read_text(encoding="utf-8"))
            self.assertEqual(records[0]["method"], "GET")
            self.assertEqual(
                records[0]["url"],
                "https://example.test/careers/search",
            )

    def test_ignores_static_and_unrelated_responses(self) -> None:
        """Avoid creating a log when no response resembles an API."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            log_path = Path(temporary_directory) / "api_discovery_log.json"
            collector = NetworkResponseCollector("example", log_path)
            static_response = cast(
                Response,
                SimpleNamespace(
                    url="https://example.test/career-logo.png",
                    status=200,
                    headers={"content-type": "image/png"},
                    request=SimpleNamespace(
                        method="get",
                        resource_type="image",
                    ),
                ),
            )
            unrelated_response = cast(
                Response,
                SimpleNamespace(
                    url="https://example.test/assets/app.js",
                    status=200,
                    headers={"content-type": "application/javascript"},
                    request=SimpleNamespace(
                        method="get",
                        resource_type="script",
                    ),
                ),
            )

            collector.handle_response(static_response)
            collector.handle_response(unrelated_response)

            self.assertFalse(log_path.exists())

    def test_ignores_career_hostname_without_api_path(self) -> None:
        """Do not match every asset merely because its host says careers."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            log_path = Path(temporary_directory) / "api_discovery_log.json"
            collector = NetworkResponseCollector("example", log_path)
            response = cast(
                Response,
                SimpleNamespace(
                    url="https://careers.example.test/assets/app.js",
                    status=200,
                    headers={"content-type": "application/javascript"},
                    request=SimpleNamespace(
                        method="get",
                        resource_type="script",
                    ),
                ),
            )

            collector.handle_response(response)

            self.assertFalse(log_path.exists())

    def test_ignores_known_analytics_json(self) -> None:
        """Exclude JSON telemetry responses from API discovery output."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            log_path = Path(temporary_directory) / "api_discovery_log.json"
            collector = NetworkResponseCollector("example", log_path)
            response = cast(
                Response,
                SimpleNamespace(
                    url="https://region1.google-analytics.com/jobs/config",
                    status=200,
                    headers={"content-type": "application/json"},
                    request=SimpleNamespace(
                        method="get",
                        resource_type="fetch",
                    ),
                ),
            )

            collector.handle_response(response)

            self.assertFalse(log_path.exists())

    def test_deduplicates_candidates_across_collectors(self) -> None:
        """Keep one durable entry for the same company, method, and URL."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            log_path = Path(temporary_directory) / "api_discovery_log.json"
            response = cast(
                Response,
                SimpleNamespace(
                    url="https://example.test/jobs/api",
                    status=200,
                    headers={"content-type": "application/json"},
                    request=SimpleNamespace(
                        method="get",
                        resource_type="fetch",
                    ),
                ),
            )

            NetworkResponseCollector("example", log_path).handle_response(
                response
            )
            NetworkResponseCollector("example", log_path).handle_response(
                response
            )

            records = json.loads(log_path.read_text(encoding="utf-8"))
            self.assertEqual(len(records), 1)

    def test_removes_legacy_noise_when_rewriting_log(self) -> None:
        """Drop old analytics entries the next time the log is updated."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            log_path = Path(temporary_directory) / "api_discovery_log.json"
            log_path.write_text(
                json.dumps(
                    [
                        {
                            "company_id": "example",
                            "url": (
                                "https://region1.google-analytics.com/"
                                "jobs/config"
                            ),
                            "method": "GET",
                            "status": 200,
                            "content_type": "application/json",
                            "resource_type": "fetch",
                        }
                    ]
                ),
                encoding="utf-8",
            )
            response = cast(
                Response,
                SimpleNamespace(
                    url="https://example.test/api/jobs",
                    status=200,
                    headers={"content-type": "application/json"},
                    request=SimpleNamespace(
                        method="get",
                        resource_type="fetch",
                    ),
                ),
            )

            NetworkResponseCollector("example", log_path).handle_response(
                response
            )

            records = json.loads(log_path.read_text(encoding="utf-8"))
            self.assertEqual(len(records), 1)
            self.assertEqual(
                records[0]["url"],
                "https://example.test/api/jobs",
            )

    def test_retries_atomic_replace_after_windows_file_lock(self) -> None:
        """Retry transient WinError 5 failures before persisting the log."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            log_path = Path(temporary_directory) / "api_discovery_log.json"
            collector = NetworkResponseCollector("orca_security", log_path)
            record = ApiDiscoveryRecord(
                company_id="orca_security",
                url="https://example.test/api/jobs",
                method="GET",
                status=200,
                content_type="application/json",
                resource_type="fetch",
                discovered_at="2026-07-30T00:00:00+00:00",
            )
            real_replace = os.replace
            attempts = 0

            def replace_after_two_locks(
                source: Path,
                destination: Path,
            ) -> None:
                nonlocal attempts
                attempts += 1
                if attempts < 3:
                    raise PermissionError(5, "Access is denied")
                real_replace(source, destination)

            with (
                patch(
                    "scrapers.browser.playwright_driver.os.replace",
                    side_effect=replace_after_two_locks,
                ) as replace,
                patch(
                    "scrapers.browser.playwright_driver.time.sleep"
                ) as sleep,
            ):
                collector._append_record(record)

            self.assertEqual(replace.call_count, 3)
            self.assertEqual(
                [call.args[0] for call in sleep.call_args_list],
                [0.1, 0.1],
            )
            records = json.loads(log_path.read_text(encoding="utf-8"))
            self.assertEqual(records[0]["company_id"], "orca_security")


class PlaywrightJobScraperTests(unittest.TestCase):
    """Exercise scraper outcomes with mocked browser resources."""

    def setUp(self) -> None:
        """Mock stealth application so browser tests stay deterministic."""

        stealth_patcher = patch(
            "scrapers.browser.playwright_driver.stealth_sync"
        )
        self.stealth = stealth_patcher.start()
        self.addCleanup(stealth_patcher.stop)

    def test_returns_waf_status_and_closes_browser_resources(self) -> None:
        """Return WAF_BLOCKED and close context and browser cleanly."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            page = MagicMock()
            page.goto.return_value = SimpleNamespace(status=200)
            page.content.return_value = (
                "<html><head><script>"
                "window.rbzns={};winsocks();"
                "</script></head><body></body></html>"
            )
            context = MagicMock()
            context.new_page.return_value = page
            browser = MagicMock()
            browser.new_context.return_value = context
            playwright = MagicMock()
            playwright.chromium.launch.return_value = browser
            manager = MagicMock()
            manager.__enter__.return_value = playwright

            scraper = PlaywrightJobScraper(
                debug_dir=temporary_directory,
                playwright_factory=MagicMock(return_value=manager),
                settle_time_ms=0,
            )
            result = scraper.scrape(
                {
                    "company_id": "rafael",
                    "api_url": "https://career.rafael.co.il/",
                    "job_selector": ".job-link",
                }
            )

            self.assertEqual(result.status, ScrapeStatus.WAF_BLOCKED)
            self.assertEqual(result.jobs, [])
            page.wait_for_selector.assert_not_called()
            context.close.assert_called_once_with()
            browser.close.assert_called_once_with()
            saved_html = Path(temporary_directory) / "rafael.html"
            self.assertTrue(saved_html.exists())

    def test_extracts_absolute_job_url_and_stable_id(self) -> None:
        """Return a normalized absolute URL and deterministic job ID."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            page = MagicMock()
            page.goto.return_value = SimpleNamespace(status=200)
            page.content.return_value = (
                '<html><body><a href="/jobs/123">'
                "Junior Software Engineer"
                "</a></body></html>"
            )
            context = MagicMock()
            context.new_page.return_value = page
            browser = MagicMock()
            browser.new_context.return_value = context
            playwright = MagicMock()
            playwright.chromium.launch.return_value = browser
            manager = MagicMock()
            manager.__enter__.return_value = playwright

            scraper = PlaywrightJobScraper(
                debug_dir=temporary_directory,
                playwright_factory=MagicMock(return_value=manager),
                settle_time_ms=0,
            )
            company = {
                "company_id": "example",
                "api_url": "https://example.test/careers",
            }

            first_result = scraper.scrape(company)
            second_result = scraper.scrape(company)

            self.assertEqual(first_result.status, ScrapeStatus.SUCCESS)
            self.assertEqual(first_result.jobs, second_result.jobs)
            self.assertEqual(
                first_result.jobs[0]["url"],
                "https://example.test/jobs/123",
            )
            self.assertEqual(first_result.jobs[0]["content"], "")
            page.locator.assert_not_called()
            page.screenshot.assert_not_called()
            self.assertFalse(
                (Path(temporary_directory) / "example.html").exists()
            )

    def test_job_selector_bypasses_universal_link_heuristics(self) -> None:
        """Extract configured DOM links even without job-like URL keywords."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            first_element = MagicMock()
            first_element.get_attribute.return_value = "/openings/123"
            first_element.inner_text.return_value = "ML"
            duplicate_element = MagicMock()
            duplicate_element.get_attribute.return_value = (
                "https://example.test/openings/123"
            )
            duplicate_element.inner_text.return_value = "Duplicate"
            selector_locator = MagicMock()
            stale_element = MagicMock()
            stale_element.get_attribute.side_effect = RuntimeError(
                "DOM node became stale"
            )
            selector_locator.all.return_value = [
                stale_element,
                first_element,
                duplicate_element,
            ]

            events: list[str] = []
            page = MagicMock()

            def navigate(*args: object, **kwargs: object) -> SimpleNamespace:
                events.append("goto")
                return SimpleNamespace(status=200)

            page.goto.side_effect = navigate
            page.wait_for_selector.side_effect = (
                lambda *args, **kwargs: events.append("selector_wait")
            )
            page.content.return_value = (
                "<html><body>Rendered careers page</body></html>"
            )
            page.locator.return_value = selector_locator
            context = MagicMock()
            context.new_page.return_value = page
            browser = MagicMock()
            browser.new_context.return_value = context
            playwright = MagicMock()
            playwright.chromium.launch.return_value = browser
            manager = MagicMock()
            manager.__enter__.return_value = playwright

            scraper = PlaywrightJobScraper(
                debug_dir=temporary_directory,
                playwright_factory=MagicMock(return_value=manager),
                settle_time_ms=0,
            )
            self.stealth.side_effect = lambda target: events.append(
                "stealth"
            )
            with patch(
                "scrapers.browser.playwright_driver.LOGGER.debug"
            ) as debug:
                result = scraper.scrape(
                    {
                        "company_id": "example",
                        "api_url": "https://example.test/careers",
                        "job_selector": ".custom-opening",
                        "selector_timeout_ms": 25_000,
                    }
                )

            self.assertEqual(result.status, ScrapeStatus.SUCCESS)
            browser.new_context.assert_called_once_with(
                user_agent=REALISTIC_USER_AGENT,
                viewport=REALISTIC_VIEWPORT,
                timezone_id="Asia/Jerusalem",
                locale="en-US",
            )
            self.stealth.assert_called_once_with(page)
            self.assertEqual(
                events,
                ["stealth", "goto", "selector_wait"],
            )
            page.add_style_tag.assert_not_called()
            page.wait_for_selector.assert_called_once_with(
                ".custom-opening",
                state="visible",
                timeout=25_000,
            )
            page.locator.assert_called_once_with(".custom-opening")
            selector_locator.all.assert_called_once_with()
            self.assertEqual(len(result.jobs), 1)
            self.assertEqual(result.jobs[0]["title"], "ML")
            self.assertEqual(
                result.jobs[0]["url"],
                "https://example.test/openings/123",
            )
            debug.assert_called_once()

    def test_selector_wait_timeout_logs_warning_and_continues(self) -> None:
        """Treat a missing SPA selector as an empty result, not a crash."""

        page = MagicMock()
        page.wait_for_selector.side_effect = PlaywrightTimeoutError(
            "selector timed out"
        )
        scraper = PlaywrightJobScraper(playwright_factory=MagicMock())

        with patch(
            "scrapers.browser.playwright_driver.LOGGER.warning"
        ) as warning:
            scraper._wait_for_job_selector(page, ".late-job")

        page.wait_for_selector.assert_called_once_with(
            ".late-job",
            state="visible",
            timeout=10_000,
        )
        warning.assert_called_once_with(
            "Selector %s not found in time",
            ".late-job",
        )

    def test_fallback_heuristic_excludes_content_urls(self) -> None:
        """Ignore article-like URLs even when they contain job keywords."""

        excluded_links = "".join(
            f'<a href="/{category}/job-guide">Content {category}</a>'
            for category in (
                "blog",
                "article",
                "story",
                "podcast",
                "meet-our-team",
            )
        )
        html = (
            f"<html><body>{excluded_links}"
            '<a href="/careers/blog-editor-role">Blog Editor Role</a>'
            '<a href="/jobs/123">Junior Software Engineer</a>'
            "</body></html>"
        )
        scraper = PlaywrightJobScraper(playwright_factory=MagicMock())

        jobs = scraper._extract_jobs(
            html=html,
            base_url="https://example.test/careers",
            company_id="example",
        )

        self.assertEqual(
            {job["url"] for job in jobs},
            {
                "https://example.test/careers/blog-editor-role",
                "https://example.test/jobs/123",
            },
        )

    def test_returns_failed_status_and_closes_after_navigation_error(
        self,
    ) -> None:
        """Return FAILED without leaking browser resources after an error."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            page = MagicMock()
            page.goto.side_effect = RuntimeError("navigation failed")
            page.content.return_value = "<html><body></body></html>"
            context = MagicMock()
            context.new_page.return_value = page
            browser = MagicMock()
            browser.new_context.return_value = context
            playwright = MagicMock()
            playwright.chromium.launch.return_value = browser
            manager = MagicMock()
            manager.__enter__.return_value = playwright

            scraper = PlaywrightJobScraper(
                debug_dir=temporary_directory,
                playwright_factory=MagicMock(return_value=manager),
            )
            result = scraper.scrape(
                {
                    "company_id": "example",
                    "api_url": "https://example.test/careers",
                }
            )

            self.assertEqual(result.status, ScrapeStatus.FAILED)
            self.assertIn("navigation failed", result.message)
            self.assertTrue(
                (Path(temporary_directory) / "example.html").exists()
            )
            page.screenshot.assert_called_once()
            context.close.assert_called_once_with()
            browser.close.assert_called_once_with()

    def test_screenshot_timeout_does_not_abort_diagnostics(self) -> None:
        """Continue writing diagnostics when screenshot capture fails."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            page = MagicMock()
            page.screenshot.side_effect = RuntimeError(
                "waiting for fonts timed out"
            )
            scraper = PlaywrightJobScraper(
                debug_dir=temporary_directory,
                playwright_factory=MagicMock(),
            )

            with patch(
                "scrapers.browser.playwright_driver.LOGGER.warning"
            ) as warning:
                paths = scraper._write_diagnostics(
                    page=page,
                    company_id="taboola",
                    html="<html><body>Jobs</body></html>",
                    status_code=200,
                    waf_reason=None,
                )

            page.screenshot.assert_called_once_with(
                path=str(Path(temporary_directory) / "taboola.png"),
                timeout=5000,
            )
            self.assertNotIn(
                str(Path(temporary_directory) / "taboola.png"),
                paths,
            )
            self.assertTrue(
                (Path(temporary_directory) / "taboola.html").exists()
            )
            self.assertTrue(
                (
                    Path(temporary_directory)
                    / "taboola_diagnostic.json"
                ).exists()
            )
            warning.assert_called_once()


class UniversalWrapperTests(unittest.TestCase):
    """Verify the legacy function returns only the discovered jobs."""

    @patch(
        "scrapers.browser.custom_adapters.PlaywrightJobScraper"
    )
    def test_wrapper_preserves_list_return_type(
        self,
        scraper_class: MagicMock,
    ) -> None:
        """Keep callers compatible with the prior list-based function."""

        expected_jobs = [
            {
                "id": "example_1",
                "title": "Student Developer",
                "location": "Israel",
                "url": "https://example.test/jobs/1",
                "content": "",
            }
        ]
        scraper_class.return_value.scrape.return_value = ScrapeResult(
            status=ScrapeStatus.SUCCESS,
            jobs=expected_jobs,
        )

        with patch("builtins.print"):
            jobs = scrape_universal_playwright(
                {
                    "company_id": "example",
                    "api_url": "https://example.test/careers",
                }
            )

        self.assertEqual(jobs, expected_jobs)


if __name__ == "__main__":
    unittest.main()
