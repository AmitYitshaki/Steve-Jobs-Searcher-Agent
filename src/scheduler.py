"""Run the job-search producer and consumer on an autonomous interval."""

from __future__ import annotations

import logging
import subprocess
import sys
import time
from collections.abc import Callable
from typing import Any, Protocol

import schedule

LOGGER = logging.getLogger(__name__)

CommandRunner = Callable[..., "subprocess.CompletedProcess[Any]"]
SleepFunction = Callable[[float], None]


class ScheduleModule(Protocol):
    """Describe the small subset of ``schedule`` used by the service."""

    def every(self, interval: int = 1) -> schedule.Job:
        """Return a job builder for the requested interval."""

    def run_pending(self) -> None:
        """Run all registered jobs whose next execution time has arrived."""


class AutonomousScheduler:
    """Run the container-safe pipeline immediately and every eight hours."""

    INTERVAL_HOURS = 8
    POLL_INTERVAL_SECONDS = 60.0
    # Each phase runs as an isolated, killable subprocess. A hung Playwright
    # scrape is force-terminated when its timeout elapses, so the scheduler
    # never blocks forever. A Python thread could detect the hang but could not
    # be terminated the same way, which is why a subprocess is used here.
    PHASE_TIMEOUTS_SECONDS = {
        "scrapers.orchestrator": 900,
        "notifications.dispatcher": 300,
    }
    TIMEOUT_EXIT_CODE = 124
    LAUNCH_FAILURE_EXIT_CODE = 127

    def __init__(
        self,
        command_runner: CommandRunner = subprocess.run,
        scheduler_module: ScheduleModule = schedule,
        sleep_function: SleepFunction = time.sleep,
    ) -> None:
        """Inject the subprocess runner and timing dependencies for testing."""

        self.command_runner = command_runner
        self.scheduler = scheduler_module
        self.sleep_function = sleep_function

    def run_cycle(self) -> None:
        """Run one producer-consumer cycle without terminating on failure."""

        LOGGER.info("Starting scheduled Steve Jobs search cycle.")
        try:
            producer_code = self._run_phase(
                module_name="scrapers.orchestrator",
                phase_name="Producer scraping phase",
            )
            if producer_code != 0:
                LOGGER.warning(
                    "Producer phase exited with code %s; skipping alert "
                    "delivery for this cycle.",
                    producer_code,
                )
                return

            consumer_code = self._run_phase(
                module_name="notifications.dispatcher",
                phase_name="Consumer alerting phase",
            )
            if consumer_code != 0:
                LOGGER.warning(
                    "Alert delivery exited with code %s; pending alerts "
                    "remain queued for the next cycle.",
                    consumer_code,
                )
                return
        except Exception:
            LOGGER.exception(
                "Scheduled job-search cycle failed; the scheduler will "
                "continue running."
            )
            return

        LOGGER.info("Scheduled Steve Jobs search cycle completed.")

    def _run_phase(self, module_name: str, phase_name: str) -> int:
        """Run one workflow module as a bounded, force-killable subprocess."""

        timeout_seconds = self.PHASE_TIMEOUTS_SECONDS[module_name]
        LOGGER.info("Starting %s: %s", phase_name, module_name)
        try:
            result = self.command_runner(
                [sys.executable, "-m", module_name],
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            LOGGER.error(
                "%s timed out after %s seconds and was terminated; the "
                "scheduler stays alive for the next cycle.",
                module_name,
                timeout_seconds,
            )
            return self.TIMEOUT_EXIT_CODE
        except FileNotFoundError:
            LOGGER.error("Could not start %s.", module_name)
            return self.LAUNCH_FAILURE_EXIT_CODE

        return result.returncode

    def serve_forever(self) -> None:
        """Run immediately, register the interval, and poll indefinitely."""

        LOGGER.info(
            "Scheduler started; job searches will run every %s hours.",
            self.INTERVAL_HOURS,
        )
        self.run_cycle()
        self.scheduler.every(self.INTERVAL_HOURS).hours.do(self.run_cycle)
        LOGGER.info(
            "Next job-search cycle scheduled in %s hours.",
            self.INTERVAL_HOURS,
        )

        while True:
            try:
                self.scheduler.run_pending()
            except Exception:
                LOGGER.exception(
                    "Scheduler polling failed; continuing to monitor jobs."
                )
            self.sleep_function(self.POLL_INTERVAL_SECONDS)


def main() -> None:
    """Configure logging and start the autonomous container scheduler."""

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )
    AutonomousScheduler().serve_forever()


if __name__ == "__main__":
    main()
