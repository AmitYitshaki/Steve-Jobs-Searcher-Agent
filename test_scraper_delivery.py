"""Tests for the Telegram-free scraping producer."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")

import scraper  # noqa: E402
from alert_queue import PendingAlert, PendingAlertQueue  # noqa: E402


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
        "description": (
            "Full job description available at: "
            "https://example.test/jobs/israel/123"
        ),
    }
    FOREIGN_JOB = {
        "id": "example_456",
        "title": "Student Software Engineer - Budapest, Hungary",
        "location": "Israel",
        "description": (
            "Full job description available at: "
            "https://example.test/jobs/budapest/456"
        ),
    }
    UNKNOWN_FOREIGN_JOB = {
        "id": "example_789",
        "title": "Student Software Engineer - Valparaiso",
        "location": "Israel",
        "description": (
            "Full job description available at: "
            "https://example.test/jobs/valparaiso/789"
        ),
    }

    def test_new_job_is_analyzed_and_queued(self) -> None:
        """Store all required fields without invoking Telegram."""

        with tempfile.TemporaryDirectory() as directory:
            queue = PendingAlertQueue(
                Path(directory) / "pending_alerts.json"
            )
            with (
                patch(
                    "scraper.load_json",
                    side_effect=[[self.COMPANY], []],
                ),
                patch(
                    "scraper.fetch_jobs_from_company",
                    return_value=[self.JOB],
                ),
                patch("scraper.analyze_job", return_value="LLM analysis"),
                patch("builtins.print"),
            ):
                scraper.run_scraper(queue=queue)

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

    def test_pending_job_is_not_analyzed_again(self) -> None:
        """Avoid repeat LLM cost while an alert is waiting for delivery."""

        with tempfile.TemporaryDirectory() as directory:
            queue = PendingAlertQueue(
                Path(directory) / "pending_alerts.json"
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
                    side_effect=[[self.COMPANY], []],
                ),
                patch(
                    "scraper.fetch_jobs_from_company",
                    return_value=[self.JOB],
                ),
                patch("scraper.analyze_job") as analyze_job,
                patch("builtins.print"),
            ):
                scraper.run_scraper(queue=queue)

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
            with (
                patch(
                    "scraper.load_json",
                    side_effect=[[self.COMPANY], []],
                ),
                patch(
                    "scraper.fetch_jobs_from_company",
                    return_value=[self.FOREIGN_JOB],
                ),
                patch("scraper.analyze_job") as analyze_job,
                patch("builtins.print") as print_output,
            ):
                scraper.run_scraper(queue=queue)

            alerts = queue.load()

        analyze_job.assert_not_called()
        self.assertEqual(alerts, [])
        self.assertTrue(
            any(
                "Budapest" in str(call_args)
                for call_args in print_output.call_args_list
            )
        )

    def test_unknown_foreign_city_is_rejected_by_strict_mode(self) -> None:
        """Reject an unlisted foreign city without spending LLM tokens."""

        with tempfile.TemporaryDirectory() as directory:
            queue = PendingAlertQueue(
                Path(directory) / "pending_alerts.json"
            )
            with (
                patch(
                    "scraper.load_json",
                    side_effect=[[self.COMPANY], []],
                ),
                patch(
                    "scraper.fetch_jobs_from_company",
                    return_value=[self.UNKNOWN_FOREIGN_JOB],
                ),
                patch("scraper.analyze_job") as analyze_job,
                patch("builtins.print") as print_output,
            ):
                scraper.run_scraper(queue=queue)

            alerts = queue.load()

        analyze_job.assert_not_called()
        self.assertEqual(alerts, [])
        self.assertTrue(
            any(
                "strict mode" in str(call_args)
                for call_args in print_output.call_args_list
            )
        )


if __name__ == "__main__":
    unittest.main()
