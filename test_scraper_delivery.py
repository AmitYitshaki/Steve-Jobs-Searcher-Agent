"""Integration-style tests for notification-aware job history updates."""

from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")

import scraper  # noqa: E402
from telegram_notifier import (  # noqa: E402
    NotificationResult,
    NotificationStatus,
)


class ScraperDeliveryTests(unittest.TestCase):
    """Verify failed alerts remain eligible for a later scraper run."""

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
        "description": "Full job description available at: test",
    }

    def test_successful_notification_is_added_to_history(self) -> None:
        """Persist a job ID only after Telegram accepts its alert."""

        result = NotificationResult(
            status=NotificationStatus.SENT,
            attempts=1,
            status_code=200,
        )

        saved_history = self._run_scraper_with_notification(result)

        self.assertIn(self.JOB["id"], saved_history)

    def test_failed_notification_stays_out_of_history(self) -> None:
        """Leave failed alerts eligible for retry on the next run."""

        result = NotificationResult(
            status=NotificationStatus.RETRY_EXHAUSTED,
            attempts=5,
            error="ConnectionError",
        )

        saved_history = self._run_scraper_with_notification(result)

        self.assertNotIn(self.JOB["id"], saved_history)

    def _run_scraper_with_notification(
        self,
        result: NotificationResult,
    ) -> list[str]:
        """Run orchestration with mocked external systems and return history."""

        notifier = MagicMock()
        notifier.send.return_value = result
        session_manager = MagicMock()
        session_manager.__enter__.return_value = MagicMock()

        with (
            patch(
                "scraper.load_json",
                side_effect=[[self.COMPANY], []],
            ),
            patch(
                "scraper.fetch_jobs_from_company",
                return_value=[self.JOB],
            ),
            patch("scraper.analyze_job", return_value="analysis"),
            patch(
                "scraper.TelegramNotifier.from_environment",
                return_value=notifier,
            ),
            patch(
                "scraper.requests.Session",
                return_value=session_manager,
            ),
            patch("scraper.save_json") as save_json,
            patch("scraper.time.sleep"),
            patch("builtins.print"),
        ):
            scraper.run_scraper()

        history_argument = save_json.call_args.args[1]
        return list(history_argument)


if __name__ == "__main__":
    unittest.main()
