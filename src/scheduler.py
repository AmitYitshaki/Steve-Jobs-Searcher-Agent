"""Run the job-search producer and consumer at fixed Israel-time daily slots."""

from __future__ import annotations

import logging
import subprocess
import sys
import time
from collections.abc import Callable
from datetime import datetime, time as time_of_day
from typing import Any
from zoneinfo import ZoneInfo

LOGGER = logging.getLogger(__name__)

CommandRunner = Callable[..., "subprocess.CompletedProcess[Any]"]
SleepFunction = Callable[[float], None]
NowProvider = Callable[[], datetime]


class AutonomousScheduler:
    """Run the container-safe pipeline once on startup and at fixed times."""

    TIMEZONE = ZoneInfo("Asia/Jerusalem")
    # Chosen to land after the morning commute, mid-afternoon, and evening --
    # when a candidate is actually likely to see and act on a Telegram alert,
    # rather than an arbitrary time derived from whenever the container last
    # happened to start.
    RUN_TIMES = (
        time_of_day(9, 0),
        time_of_day(14, 0),
        time_of_day(19, 0),
    )
    # A poll can be delayed by a slow run_cycle() or scheduler jitter, so a
    # due slot is honored for a window after its exact minute rather than
    # requiring an exact-second match, which polling every 60s cannot
    # guarantee.
    CATCH_UP_WINDOW_SECONDS = 5 * 60
    POLL_INTERVAL_SECONDS = 60.0
    # Each phase runs as an isolated, killable subprocess. A hung Playwright
    # scrape is force-terminated when its timeout elapses, so the scheduler
    # never blocks forever. A Python thread could detect the hang but could not
    # be terminated the same way, which is why a subprocess is used here.
    # Sized from measured throughput: a 55-company scan took ~423s wall
    # clock (~7.7s/company, dominated by browser adapters at ~13s each).
    # The producer budget covers a ~200-company catalogue plus LLM analysis
    # with headroom. This is a watchdog, not a scan budget: it bounds a
    # totally hung phase, so it must stay well above a healthy run's length.
    # Keep in sync with pipeline.E2ERunner.SCRIPT_TIMEOUTS.
    PHASE_TIMEOUTS_SECONDS = {
        "scrapers.orchestrator": 3600,
        "notifications.dispatcher": 600,
    }
    TIMEOUT_EXIT_CODE = 124
    LAUNCH_FAILURE_EXIT_CODE = 127

    def __init__(
        self,
        command_runner: CommandRunner = subprocess.run,
        sleep_function: SleepFunction = time.sleep,
        now_provider: NowProvider | None = None,
    ) -> None:
        """Inject the subprocess runner and timing dependencies for testing."""

        self.command_runner = command_runner
        self.sleep_function = sleep_function
        self.now_provider = now_provider or (
            lambda: datetime.now(self.TIMEZONE)
        )
        self._last_run_marker: str | None = None

    def run_cycle(self) -> None:
        """Run one producer-consumer cycle without terminating on failure."""

        LOGGER.info("Starting scheduled Steve Jobs search cycle.")
        try:
            producer_code = self._run_phase(
                module_name="scrapers.orchestrator",
                phase_name="Producer scraping phase",
            )
            if producer_code != 0:
                # Delivery is deliberately NOT skipped. The queue is durable
                # and can still hold alerts analyzed in an earlier cycle; a
                # failed scrape must not strand work that is ready to send.
                LOGGER.warning(
                    "Producer phase exited with code %s; still delivering "
                    "any alerts already queued.",
                    producer_code,
                )

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

        if producer_code != 0:
            # The consumer ran and may have delivered queued work, but the
            # scan itself did not complete. Never report that as a clean cycle.
            LOGGER.warning(
                "Scheduled cycle finished with a failed producer "
                "(code %s); alert delivery still ran.",
                producer_code,
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

    def _due_run_marker(self, now: datetime) -> str | None:
        """Return a unique marker for the run slot currently due, if any.

        A slot is due once `now` has reached its target time and is still
        within ``CATCH_UP_WINDOW_SECONDS`` of it -- wide enough to absorb
        60-second poll jitter, narrow enough that a missed window is simply
        skipped until the next slot rather than firing hours late.
        """

        for target in self.RUN_TIMES:
            target_today = now.replace(
                hour=target.hour,
                minute=target.minute,
                second=0,
                microsecond=0,
            )
            elapsed = (now - target_today).total_seconds()
            if 0 <= elapsed < self.CATCH_UP_WINDOW_SECONDS:
                return f"{now.date().isoformat()}T{target.isoformat()}"
        return None

    def serve_forever(self) -> None:
        """Run immediately, then at each fixed Israel-time slot, forever."""

        LOGGER.info(
            "Scheduler started; job searches will run daily at %s Israel "
            "time.",
            ", ".join(t.strftime("%H:%M") for t in self.RUN_TIMES),
        )
        self.run_cycle()

        while True:
            try:
                now = self.now_provider()
                marker = self._due_run_marker(now)
                if marker is not None and marker != self._last_run_marker:
                    self._last_run_marker = marker
                    self.run_cycle()
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
