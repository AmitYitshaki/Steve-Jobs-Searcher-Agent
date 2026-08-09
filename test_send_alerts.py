"""Tests for transactional pending-alert delivery."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, call, patch

from notifications.dispatcher import AlertConsumer
from notifications.telegram.bot import (
    NotificationResult,
    NotificationStatus,
)
from storage.history import JobHistoryStore
from storage.queue import PendingAlert, PendingAlertQueue


class AlertConsumerTests(unittest.TestCase):
    """Verify successful sends commit and failed sends remain queued."""

    def setUp(self) -> None:
        """Create isolated stores and one queued alert."""

        self.temporary_directory = tempfile.TemporaryDirectory()
        root = Path(self.temporary_directory.name)
        self.queue = PendingAlertQueue(root / "pending_alerts.json")
        self.history = JobHistoryStore(root / "jobs_history.json")
        self.alert = PendingAlert(
            job_id="job-1",
            company_name="Example",
            job_url="https://example.test/jobs/1",
            llm_summary="Telegram-ready summary",
        )
        self.queue.append(self.alert)
        self.notifier = MagicMock()

    def tearDown(self) -> None:
        """Remove isolated runtime files."""

        self.temporary_directory.cleanup()

    def test_success_adds_history_before_removing_queue_record(self) -> None:
        """Commit delivery history before deleting the pending alert."""

        self.notifier.send.return_value = NotificationResult(
            status=NotificationStatus.SENT,
            attempts=1,
            status_code=200,
        )
        operations: list[str] = []
        original_add = self.history.add
        original_remove = self.queue.remove

        def recording_add(job_id: str) -> bool:
            """Record and delegate a history mutation."""

            operations.append("history")
            return original_add(job_id)

        def recording_remove(job_id: str) -> bool:
            """Record and delegate a queue mutation."""

            operations.append("queue")
            return original_remove(job_id)

        with (
            patch.object(self.history, "add", side_effect=recording_add),
            patch.object(self.queue, "remove", side_effect=recording_remove),
            patch("builtins.print"),
        ):
            summary = self._consumer().run()

        self.assertEqual(operations, ["history", "queue"])
        self.assertEqual(self.history.load(), {"job-1"})
        self.assertEqual(self.queue.load(), [])
        self.assertEqual(summary.sent, 1)
        self.assertEqual(summary.failed, 0)

    def test_permanent_failure_remains_pending(self) -> None:
        """Keep a permanently failed alert for a later VPN-enabled run."""

        self.notifier.send.return_value = NotificationResult(
            status=NotificationStatus.PERMANENT_FAILURE,
            attempts=1,
            status_code=401,
            error="Telegram HTTP 401",
        )

        with patch("builtins.print"):
            summary = self._consumer().run()

        self.assertEqual(self.queue.load(), [self.alert])
        self.assertEqual(self.history.load(), set())
        self.assertEqual(summary.failed, 1)

    def test_retry_exhaustion_does_not_block_later_alerts(self) -> None:
        """Retain one failure while committing a later successful alert."""

        second_alert = PendingAlert(
            job_id="job-2",
            company_name="Other",
            job_url="https://example.test/jobs/2",
            llm_summary="Second summary",
        )
        self.queue.append(second_alert)
        self.notifier.send.side_effect = [
            NotificationResult(
                status=NotificationStatus.RETRY_EXHAUSTED,
                attempts=3,
                error="ConnectionResetError",
            ),
            NotificationResult(
                status=NotificationStatus.SENT,
                attempts=1,
                status_code=200,
            ),
        ]

        with patch("builtins.print"):
            summary = self._consumer().run()

        self.assertEqual(self.notifier.send.call_args_list, [
            call("Telegram-ready summary"),
            call("Second summary"),
        ])
        self.assertEqual(self.queue.load(), [self.alert])
        self.assertEqual(self.history.load(), {"job-2"})
        self.assertEqual(summary.sent, 1)
        self.assertEqual(summary.failed, 1)

    def test_history_record_recovers_interrupted_queue_removal(self) -> None:
        """Remove an already-delivered stale record without resending it."""

        self.history.add("job-1")

        with patch("builtins.print"):
            summary = self._consumer().run()

        self.notifier.send.assert_not_called()
        self.assertEqual(self.queue.load(), [])
        self.assertEqual(summary.skipped, 1)

    def _consumer(self) -> AlertConsumer:
        """Build a consumer from this test's isolated dependencies."""

        return AlertConsumer(
            queue=self.queue,
            history=self.history,
            notifier=self.notifier,
        )


if __name__ == "__main__":
    unittest.main()
