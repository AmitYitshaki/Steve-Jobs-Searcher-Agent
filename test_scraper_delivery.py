"""Tests for the Telegram-free scraping producer."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")

import scraper  # noqa: E402
from alert_queue import (  # noqa: E402
    JobHistoryStore,
    PendingAlert,
    PendingAlertQueue,
)


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
                    "scraper.load_json",
                    side_effect=[[self.COMPANY]],
                ),
                patch(
                    "scraper.fetch_jobs_from_company",
                    return_value=[self.JOB],
                ),
                patch(
                    "scraper.analyze_job",
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
                    "scraper.load_json",
                    side_effect=[[html_company]],
                ),
                patch(
                    "scraper.fetch_jobs_from_company",
                    return_value=[self.HTML_TITLE_JOB],
                ),
                patch(
                    "scraper.analyze_job",
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
                    "scraper.load_json",
                    side_effect=[[self.COMPANY]],
                ),
                patch(
                    "scraper.fetch_jobs_from_company",
                    return_value=[self.JOB],
                ),
                patch("scraper.analyze_job") as analyze_job,
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
                    "scraper.load_json",
                    side_effect=[[self.COMPANY]],
                ),
                patch(
                    "scraper.fetch_jobs_from_company",
                    return_value=[self.FOREIGN_JOB],
                ),
                patch("scraper.analyze_job") as analyze_job,
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
                    "scraper.load_json",
                    side_effect=[[self.COMPANY]],
                ),
                patch(
                    "scraper.fetch_jobs_from_company",
                    return_value=[self.UNKNOWN_FOREIGN_JOB],
                ),
                patch(
                    "scraper.analyze_job",
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


if __name__ == "__main__":
    unittest.main()
