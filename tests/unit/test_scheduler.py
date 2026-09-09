"""Tests for the autonomous container scheduler."""

from __future__ import annotations

import subprocess
import sys
import unittest
from unittest.mock import MagicMock

from scheduler import AutonomousScheduler, ScheduleModule

PRODUCER_TIMEOUT = AutonomousScheduler.PHASE_TIMEOUTS_SECONDS[
    "scrapers.orchestrator"
]


def _completed(returncode: int) -> "subprocess.CompletedProcess[bytes]":
    """Build a minimal completed-process stub for the injected runner."""

    return subprocess.CompletedProcess(args=[], returncode=returncode)


class AutonomousSchedulerTests(unittest.TestCase):
    """Verify immediate execution, interval registration, and resilience."""

    def setUp(self) -> None:
        """Create isolated subprocess and timing dependencies."""

        self.command_runner = MagicMock(return_value=_completed(0))
        self.scheduler_module = MagicMock(spec=ScheduleModule)
        self.sleep_function = MagicMock(side_effect=KeyboardInterrupt)
        self.scheduler = AutonomousScheduler(
            command_runner=self.command_runner,
            scheduler_module=self.scheduler_module,
            sleep_function=self.sleep_function,
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

    def test_serve_forever_runs_immediately_and_schedules_eight_hours(
        self,
    ) -> None:
        """Run at startup before polling the registered interval job."""

        interval = MagicMock()
        self.scheduler_module.every.return_value = interval

        with self.assertRaises(KeyboardInterrupt):
            self.scheduler.serve_forever()

        self.assertEqual(
            self._launched_modules(),
            ["scrapers.orchestrator", "notifications.dispatcher"],
        )
        self.scheduler_module.every.assert_called_once_with(8)
        interval.hours.do.assert_called_once_with(self.scheduler.run_cycle)
        self.scheduler_module.run_pending.assert_called_once_with()
        self.sleep_function.assert_called_once_with(60.0)


if __name__ == "__main__":
    unittest.main()
