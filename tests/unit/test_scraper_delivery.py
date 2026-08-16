"""Tests for the Telegram-free scraping producer."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")

from scrapers import orchestrator as scraper  # noqa: E402
from storage.history import JobHistoryStore  # noqa: E402
from storage.queue import PendingAlert, PendingAlertQueue  # noqa: E402


class ScraperProducerTests(unittest.TestCase):
    """Verify relevant jobs are analyzed once and durably queued."""

    COMPANY = {
        "company_id": "example",
        "company_name": "Example",
        "ats_type": "greenhouse",
        "api_url": "https://example.test/jobs",
        "location_filters": ["Israel"],
    }
    JOB = {
        "id": "example_123",
        "title": "Student Software Engineer",
        "location": "Israel",
        "url": "https://example.test/jobs/israel/123",
        "content": "Build Python services. B.Sc. students only.",
    }
    FOREIGN_JOB = {
        "id": "example_456",
        "title": "Student Software Engineer - Budapest, Hungary",
        "location": "Israel",
        "url": "https://example.test/jobs/budapest/456",
        "content": "Build Python services.",
    }
    UNKNOWN_FOREIGN_JOB = {
        "id": "example_789",
        "title": "Student Software Engineer - Valparaiso",
        "location": "Israel",
        "url": "https://example.test/jobs/valparaiso/789",
        "content": "Build Python services.",
    }
    HTML_TITLE_JOB = {
        "id": "example_999",
        "title": "Student Software Engineer <R&D> - Israel",
        "location": "Tel Aviv & Central, Israel",
        "url": (
            "https://example.test/jobs/israel/999"
            "?team=R%26D&level=student"
        ),
        "content": "Build Python services.",
    }

    def test_title_decision_rejects_non_rd_entry_level_roles(self) -> None:
        """Reject explicit business functions despite internship signals."""

        cases = (
            "Sales Development Representative (SDR - Internship)",
            "Marketing Intern",
            "Human Resources Student",
            "Business Development Intern",
        )

        for title in cases:
            with self.subTest(title=title):
                decision = scraper.is_relevant_job(title)
                self.assertFalse(decision.allowed)
                self.assertEqual(
                    decision.reason,
                    "excluded title keyword",
                )
                self.assertIsNotNone(decision.matched_keyword)

    def test_title_decision_preserves_strong_high_recall_signal(self) -> None:
        """Keep hardware student roles under the high-recall policy."""

        decision = scraper.is_relevant_job("Chip Design Student")

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.reason, "strong entry-level signal")
        self.assertEqual(decision.matched_keyword, "student")

    def test_graduate_software_dev_title_is_relevant(self) -> None:
        """Accept Amazon's graduate software-development abbreviation."""

        decision = scraper.is_relevant_job(
            "2026 Graduate Software Dev Engineer"
        )

        self.assertTrue(decision.allowed)
        self.assertEqual(
            decision.reason,
            "weak entry-level and target-role signals",
        )
        self.assertEqual(decision.matched_keyword, "graduate")

    def test_graduate_keyword_has_negative_controls(self) -> None:
        """Avoid substring, seniority, and unrelated-program matches."""

        titles = (
            "Undergraduate Software Engineer",
            "Graduate Program Manager",
            "MBA Graduate Finance Program",
        )

        for title in titles:
            with self.subTest(title=title):
                self.assertFalse(scraper.is_relevant_job(title).allowed)

    def test_non_relevant_title_returns_structured_reason(self) -> None:
        """Explain why an otherwise valid title did not qualify."""

        decision = scraper.is_relevant_job("Office Administrator")

        self.assertFalse(decision.allowed)
        self.assertEqual(
            decision.reason,
            "no qualifying entry-level title signal",
        )
        self.assertIsNone(decision.matched_keyword)

    def test_title_rejection_is_logged_before_analysis(self) -> None:
        """Expose deterministic title rejections in the Producer log."""

        sales_job = {
            **self.JOB,
            "title": "Sales Development Representative (SDR - Internship)",
        }
        with tempfile.TemporaryDirectory() as directory:
            queue = PendingAlertQueue(
                Path(directory) / "pending_alerts.json"
            )
            history_store = JobHistoryStore(
                Path(directory) / "jobs_history.json"
            )
            with (
                patch(
                    "scrapers.orchestrator.load_json",
                    side_effect=[[self.COMPANY]],
                ),
                patch(
                    "scrapers.orchestrator.fetch_jobs_from_company",
                    return_value=[sales_job],
                ),
                patch(
                    "scrapers.orchestrator.analyze_job"
                ) as analyze_job,
                patch("scrapers.orchestrator.logging.info") as info,
                patch("builtins.print"),
            ):
                scraper.run_scraper(
                    queue=queue,
                    history_store=history_store,
                )

            alerts = queue.load()

        self.assertEqual(alerts, [])
        analyze_job.assert_not_called()
        self.assertTrue(
            any(
                call_args.args[0].startswith("Rejecting %s: title")
                for call_args in info.call_args_list
            )
        )

    def test_new_job_is_analyzed_and_queued(self) -> None:
        """Store all required fields without invoking Telegram."""

        with tempfile.TemporaryDirectory() as directory:
            queue = PendingAlertQueue(
                Path(directory) / "pending_alerts.json"
            )
            history_store = JobHistoryStore(
                Path(directory) / "jobs_history.json"
            )
            with (
                patch(
                    "scrapers.orchestrator.load_json",
                    side_effect=[[self.COMPANY]],
                ),
                patch(
                    "scrapers.orchestrator.fetch_jobs_from_company",
                    return_value=[self.JOB],
                ),
                patch(
                    "scrapers.orchestrator.analyze_job",
                    return_value="LLM analysis",
                ) as analyze_job,
                patch("builtins.print"),
            ):
                scraper.run_scraper(
                    queue=queue,
                    history_store=history_store,
                )

            alerts = queue.load()

        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].job_id, "example_123")
        self.assertEqual(alerts[0].company_name, "Example")
        self.assertEqual(
            alerts[0].job_url,
            "https://example.test/jobs/israel/123",
        )
        self.assertIn("LLM analysis", alerts[0].llm_summary)
        self.assertIn("Student Software Engineer", alerts[0].llm_summary)
        analyze_job.assert_called_once_with(
            job_title="Student Software Engineer",
            job_location="Israel",
            job_content="Build Python services. B.Sc. students only.",
        )

    def test_alert_header_uses_safe_html_formatting(self) -> None:
        """Bold the header while escaping title and location text."""

        with tempfile.TemporaryDirectory() as directory:
            queue = PendingAlertQueue(
                Path(directory) / "pending_alerts.json"
            )
            history_store = JobHistoryStore(
                Path(directory) / "jobs_history.json"
            )
            html_company = {
                **self.COMPANY,
                "company_name": "Example <Labs> & Co",
            }
            with (
                patch(
                    "scrapers.orchestrator.load_json",
                    side_effect=[[html_company]],
                ),
                patch(
                    "scrapers.orchestrator.fetch_jobs_from_company",
                    return_value=[self.HTML_TITLE_JOB],
                ),
                patch(
                    "scrapers.orchestrator.analyze_job",
                    return_value="<b>ניתוח</b>",
                ),
                patch("builtins.print"),
            ):
                scraper.run_scraper(
                    queue=queue,
                    history_store=history_store,
                )

            summary = queue.load()[0].llm_summary

        self.assertIn(
            "<b>משרה חדשה נמצאה: Student Software Engineer "
            "&lt;R&amp;D&gt; - Israel</b>",
            summary,
        )
        self.assertIn(
            "🏢 חברה: Example &lt;Labs&gt; &amp; Co",
            summary,
        )
        self.assertIn("Tel Aviv &amp; Central, Israel", summary)
        self.assertIn(
            "🔗 קישור: https://example.test/jobs/israel/999"
            "?team=R%26D&amp;level=student",
            summary,
        )
        self.assertIn("<b>ניתוח</b>", summary)
        self.assertNotIn("**", summary)

    def test_pending_job_is_not_analyzed_again(self) -> None:
        """Avoid repeat LLM cost while an alert is waiting for delivery."""

        with tempfile.TemporaryDirectory() as directory:
            queue = PendingAlertQueue(
                Path(directory) / "pending_alerts.json"
            )
            history_store = JobHistoryStore(
                Path(directory) / "jobs_history.json"
            )
            queue.append(
                PendingAlert(
                    job_id="example_123",
                    company_name="Example",
                    job_url="https://example.test/jobs/123",
                    llm_summary="Already analyzed",
                )
            )
            with (
                patch(
                    "scrapers.orchestrator.load_json",
                    side_effect=[[self.COMPANY]],
                ),
                patch(
                    "scrapers.orchestrator.fetch_jobs_from_company",
                    return_value=[self.JOB],
                ),
                patch(
                    "scrapers.orchestrator.analyze_job"
                ) as analyze_job,
                patch("builtins.print"),
            ):
                scraper.run_scraper(
                    queue=queue,
                    history_store=history_store,
                )

            alerts = queue.load()

        analyze_job.assert_not_called()
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].llm_summary, "Already analyzed")

    def test_foreign_similar_job_is_rejected_before_analysis(self) -> None:
        """Drop a geographic leak even when its adapter says Israel."""

        with tempfile.TemporaryDirectory() as directory:
            queue = PendingAlertQueue(
                Path(directory) / "pending_alerts.json"
            )
            history_store = JobHistoryStore(
                Path(directory) / "jobs_history.json"
            )
            with (
                patch(
                    "scrapers.orchestrator.load_json",
                    side_effect=[[self.COMPANY]],
                ),
                patch(
                    "scrapers.orchestrator.fetch_jobs_from_company",
                    return_value=[self.FOREIGN_JOB],
                ),
                patch(
                    "scrapers.orchestrator.analyze_job"
                ) as analyze_job,
                patch("builtins.print") as print_output,
            ):
                scraper.run_scraper(
                    queue=queue,
                    history_store=history_store,
                )

            alerts = queue.load()

        analyze_job.assert_not_called()
        self.assertEqual(alerts, [])
        self.assertTrue(
            any(
                "Budapest" in str(call_args)
                for call_args in print_output.call_args_list
            )
        )

    def test_unknown_location_is_allowed_in_medium_mode(self) -> None:
        """Allow unknown locations unless the blacklist identifies them."""

        with tempfile.TemporaryDirectory() as directory:
            queue = PendingAlertQueue(
                Path(directory) / "pending_alerts.json"
            )
            history_store = JobHistoryStore(
                Path(directory) / "jobs_history.json"
            )
            with (
                patch(
                    "scrapers.orchestrator.load_json",
                    side_effect=[[self.COMPANY]],
                ),
                patch(
                    "scrapers.orchestrator.fetch_jobs_from_company",
                    return_value=[self.UNKNOWN_FOREIGN_JOB],
                ),
                patch(
                    "scrapers.orchestrator.analyze_job",
                    return_value="LLM analysis",
                ) as analyze_job,
                patch("builtins.print"),
            ):
                scraper.run_scraper(
                    queue=queue,
                    history_store=history_store,
                )

            alerts = queue.load()

        analyze_job.assert_called_once_with(
            job_title="Student Software Engineer - Valparaiso",
            job_location="Israel",
            job_content="Build Python services.",
        )
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].job_id, "example_789")


    def test_heartbeat_sent_when_no_new_jobs(self) -> None:
        """Emit the heartbeat so a quiet, successful run is never silent."""

        notifier = MagicMock()
        with tempfile.TemporaryDirectory() as directory:
            queue = PendingAlertQueue(
                Path(directory) / "pending_alerts.json"
            )
            history_store = JobHistoryStore(
                Path(directory) / "jobs_history.json"
            )
            with (
                patch(
                    "scrapers.orchestrator.load_json",
                    side_effect=[[self.COMPANY]],
                ),
                patch(
                    "scrapers.orchestrator.fetch_jobs_from_company",
                    return_value=[],
                ),
                patch(
                    "scrapers.orchestrator.analyze_job"
                ) as analyze_job,
                patch("builtins.print"),
            ):
                scraper.run_scraper(
                    queue=queue,
                    history_store=history_store,
                    heartbeat_notifier=notifier,
                )

        analyze_job.assert_not_called()
        notifier.send.assert_called_once_with(
            "Scraping cycle completed. 0 new jobs found."
        )

    def test_heartbeat_not_sent_when_new_jobs_found(self) -> None:
        """Stay silent on the heartbeat channel when real jobs were queued."""

        notifier = MagicMock()
        with tempfile.TemporaryDirectory() as directory:
            queue = PendingAlertQueue(
                Path(directory) / "pending_alerts.json"
            )
            history_store = JobHistoryStore(
                Path(directory) / "jobs_history.json"
            )
            with (
                patch(
                    "scrapers.orchestrator.load_json",
                    side_effect=[[self.COMPANY]],
                ),
                patch(
                    "scrapers.orchestrator.fetch_jobs_from_company",
                    return_value=[self.JOB],
                ),
                patch(
                    "scrapers.orchestrator.analyze_job",
                    return_value="LLM analysis",
                ),
                patch("builtins.print"),
            ):
                scraper.run_scraper(
                    queue=queue,
                    history_store=history_store,
                    heartbeat_notifier=notifier,
                )

        notifier.send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
