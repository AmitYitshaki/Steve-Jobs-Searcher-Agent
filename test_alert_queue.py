"""Tests for durable alert queue and history storage."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from storage.drivers.atomic_json import AtomicJsonListStore
from storage.history import JobHistoryStore
from storage.queue import PendingAlert, PendingAlertQueue


class AlertQueueTests(unittest.TestCase):
    """Verify queue mutations are validated and deduplicated."""

    def setUp(self) -> None:
        """Create isolated runtime paths for each test."""

        self.temporary_directory = tempfile.TemporaryDirectory()
        root = Path(self.temporary_directory.name)
        self.queue_path = root / "pending_alerts.json"
        self.history_path = root / "jobs_history.json"
        self.alert = PendingAlert(
            job_id="job-1",
            company_name="Example",
            job_url="https://example.test/jobs/1",
            llm_summary="Formatted summary",
        )

    def tearDown(self) -> None:
        """Remove isolated runtime files."""

        self.temporary_directory.cleanup()

    def test_append_deduplicates_by_job_id(self) -> None:
        """Append each job only once and preserve its complete record."""

        queue = PendingAlertQueue(self.queue_path)

        self.assertTrue(queue.append(self.alert))
        self.assertFalse(queue.append(self.alert))
        self.assertEqual(queue.load(), [self.alert])

    def test_remove_preserves_other_alerts(self) -> None:
        """Remove only the delivered record from the queue."""

        second_alert = PendingAlert(
            job_id="job-2",
            company_name="Other",
            job_url="https://example.test/jobs/2",
            llm_summary="Second summary",
        )
        queue = PendingAlertQueue(self.queue_path)
        queue.append(self.alert)
        queue.append(second_alert)

        self.assertTrue(queue.remove("job-1"))
        self.assertEqual(queue.load(), [second_alert])

    def test_history_add_is_idempotent(self) -> None:
        """Persist a delivered job ID only once."""

        history = JobHistoryStore(self.history_path)

        self.assertTrue(history.add("job-1"))
        self.assertFalse(history.add("job-1"))
        self.assertEqual(history.load(), {"job-1"})

    def test_corrupt_queue_fails_without_overwriting_it(self) -> None:
        """Surface malformed state instead of silently losing alerts."""

        original = '{"unexpected": true}'
        self.queue_path.write_text(original, encoding="utf-8")

        with self.assertRaises(ValueError):
            PendingAlertQueue(self.queue_path).append(self.alert)

        self.assertEqual(
            self.queue_path.read_text(encoding="utf-8"),
            original,
        )

    def test_atomic_replace_retries_transient_windows_lock(self) -> None:
        """Retry access-denied replacement after closing the JSON handle."""

        real_replace = os.replace
        sleep_function = MagicMock()
        store = AtomicJsonListStore(
            self.history_path,
            sleep_function=sleep_function,
        )
        attempts = 0

        def replace_after_two_locks(
            source: str | Path,
            destination: str | Path,
        ) -> None:
            """Simulate antivirus locks, then perform the real replacement."""

            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise PermissionError(5, "Access is denied")
            real_replace(source, destination)

        with patch(
            "storage.drivers.atomic_json.os.replace",
            side_effect=replace_after_two_locks,
        ):
            store.write(["job-1"])

        self.assertEqual(attempts, 3)
        delays = [
            call_args.args[0]
            for call_args in sleep_function.call_args_list
        ]
        self.assertEqual(delays, [0.1, 0.2])
        self.assertEqual(store.read(), ["job-1"])

    def test_atomic_replace_stops_after_five_lock_failures(self) -> None:
        """Raise after five Windows lock failures without corrupting state."""

        sleep_function = MagicMock()
        store = AtomicJsonListStore(
            self.history_path,
            sleep_function=sleep_function,
        )

        with (
            patch(
                "storage.drivers.atomic_json.os.replace",
                side_effect=PermissionError(5, "Access is denied"),
            ) as replace,
            self.assertRaises(PermissionError),
        ):
            store.write(["job-1"])

        self.assertEqual(replace.call_count, 5)
        delays = [
            call_args.args[0]
            for call_args in sleep_function.call_args_list
        ]
        self.assertEqual(len(delays), 4)
        for actual, expected in zip(delays, [0.1, 0.2, 0.3, 0.4]):
            self.assertAlmostEqual(actual, expected)
        self.assertFalse(self.history_path.exists())
        self.assertEqual(
            list(self.history_path.parent.glob(".jobs_history.json.*.tmp")),
            [],
        )


if __name__ == "__main__":
    unittest.main()
