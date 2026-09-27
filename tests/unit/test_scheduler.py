"""Tests for the autonomous container scheduler."""

from __future__ import annotations

import subprocess
import sys
import unittest
from datetime import datetime
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

from scheduler import AutonomousScheduler

PRODUCER_TIMEOUT = AutonomousScheduler.PHASE_TIMEOUTS_SECONDS[
    "scrapers.orchestrator"
]
ISRAEL = ZoneInfo("Asia/Jerusalem")


def _completed(returncode: int) -> "subprocess.CompletedProcess[bytes]":
    """Build a minimal completed-process stub for the injected runner."""

    return subprocess.CompletedProcess(args=[], returncode=returncode)


def _at(hour: int, minute: int, day: int = 15) -> datetime:
    """Build an Israel-time datetime for a fixed 2026-09 test day."""

    return datetime(2026, 9, day, hour, minute, tzinfo=ISRAEL)


class AutonomousSchedulerTests(unittest.TestCase):
    """Verify immediate execution, fixed run times, and resilience."""

    def setUp(self) -> None:
        """Create isolated subprocess and timing dependencies."""

        self.command_runner = MagicMock(return_value=_completed(0))
        self.sleep_function = MagicMock(side_effect=KeyboardInterrupt)
        self.now_provider = MagicMock(return_value=_at(10, 0))
        self.scheduler = AutonomousScheduler(
            command_runner=self.command_runner,
            sleep_function=self.sleep_function,
            now_provider=self.now_provider,
        )

    def _launched_modules(self) -> list[str]:
        """Return the module name from each recorded subprocess launch."""

        return [
            call.args[0][2]
            for call in self.command_runner.call_args_list
        ]

    def test_run_cycle_launches_producer_before_consumer(self) -> None:
        """Execute both container-safe phases in their required order."""

        self.scheduler.run_cycle()

        self.assertEqual(
            self._launched_modules(),
            ["scrapers.orchestrator", "notifications.dispatcher"],
        )

    def test_run_cycle_still_delivers_when_producer_fails(self) -> None:
        """Deliver already-queued alerts even when the scrape phase fails.

        The queue is durable and can hold alerts analyzed in an earlier
        cycle. Gating delivery on a fresh successful scrape stranded that
        work until the next healthy cycle.
        """

        self.command_runner.return_value = _completed(1)

        self.scheduler.run_cycle()

        self.assertEqual(
            self._launched_modules(),
            ["scrapers.orchestrator", "notifications.dispatcher"],
        )

    def test_run_cycle_survives_producer_timeout(self) -> None:
        """Keep a hung, timed-out phase from crashing the scheduler."""

        self.command_runner.side_effect = subprocess.TimeoutExpired(
            cmd="scrapers.orchestrator",
            timeout=PRODUCER_TIMEOUT,
        )

        # Must not raise. A timed-out producer is a failed producer, but
        # delivery of previously queued alerts still runs.
        self.scheduler.run_cycle()

        self.assertEqual(
            self._launched_modules(),
            ["scrapers.orchestrator", "notifications.dispatcher"],
        )

    def test_run_cycle_uses_current_interpreter_and_timeout(self) -> None:
        """Launch phases with the active interpreter under a bounded timeout."""

        self.scheduler.run_cycle()

        producer_call = self.command_runner.call_args_list[0]
        self.assertEqual(
            producer_call.args[0],
            [sys.executable, "-m", "scrapers.orchestrator"],
        )
        self.assertEqual(producer_call.kwargs["timeout"], PRODUCER_TIMEOUT)

    def test_due_run_marker_matches_exact_slot_time(self) -> None:
        """Recognize the precise target minute as due."""

        marker = self.scheduler._due_run_marker(_at(9, 0))

        self.assertIsNotNone(marker)

    def test_due_run_marker_within_catch_up_window(self) -> None:
        """Tolerate poll jitter shortly after the exact target minute."""

        marker = self.scheduler._due_run_marker(_at(9, 4))

        self.assertIsNotNone(marker)

    def test_due_run_marker_outside_catch_up_window_is_none(self) -> None:
        """Do not fire hours late for a slot the poller missed entirely."""

        self.assertIsNone(self.scheduler._due_run_marker(_at(9, 30)))
        self.assertIsNone(self.scheduler._due_run_marker(_at(11, 0)))

    def test_due_run_marker_before_slot_is_none(self) -> None:
        """Never fire a slot before its target time arrives."""

        self.assertIsNone(self.scheduler._due_run_marker(_at(8, 59)))

    def test_due_run_marker_distinguishes_all_three_daily_slots(self) -> None:
        """Recognize 09:00, 14:00, and 19:00 as independently due."""

        markers = {
            self.scheduler._due_run_marker(_at(9, 0)),
            self.scheduler._due_run_marker(_at(14, 0)),
            self.scheduler._due_run_marker(_at(19, 0)),
        }

        self.assertEqual(len(markers), 3)
        self.assertNotIn(None, markers)

    def test_serve_forever_runs_immediately_when_no_slot_is_due(self) -> None:
        """Prove liveness on startup even between scheduled slots."""

        self.now_provider.return_value = _at(10, 0)

        with self.assertRaises(KeyboardInterrupt):
            self.scheduler.serve_forever()

        self.assertEqual(
            self._launched_modules(),
            ["scrapers.orchestrator", "notifications.dispatcher"],
        )
        self.sleep_function.assert_called_once_with(60.0)

    def test_serve_forever_triggers_a_second_cycle_at_a_due_slot(
        self,
    ) -> None:
        """Run again once polling detects a fixed Israel-time slot is due."""

        self.now_provider.return_value = _at(14, 1)

        with self.assertRaises(KeyboardInterrupt):
            self.scheduler.serve_forever()

        # Startup run + the 14:00 slot = two full producer/consumer cycles.
        self.assertEqual(
            self._launched_modules(),
            [
                "scrapers.orchestrator",
                "notifications.dispatcher",
                "scrapers.orchestrator",
                "notifications.dispatcher",
            ],
        )

    def test_serve_forever_does_not_refire_the_same_slot_twice(self) -> None:
        """Poll the same due slot on consecutive ticks without repeating it."""

        self.now_provider.return_value = _at(14, 1)
        self.sleep_function.side_effect = [None, KeyboardInterrupt]

        with self.assertRaises(KeyboardInterrupt):
            self.scheduler.serve_forever()

        # Startup run + one 14:00 run, NOT two 14:00 runs across both polls.
        self.assertEqual(
            self._launched_modules(),
            [
                "scrapers.orchestrator",
                "notifications.dispatcher",
                "scrapers.orchestrator",
                "notifications.dispatcher",
            ],
        )


if __name__ == "__main__":
    unittest.main()
