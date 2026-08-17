"""Per-company scraper-health calculations and terminal summaries."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import Any

NowProvider = Callable[[], datetime]


class CompanyHealthTracker:
    """Accumulate one company's funnel metrics and derive durable health."""

    HISTORY_WINDOW_SIZE = 20
    SILENT_BREAKAGE_RUN_THRESHOLD = 3

    def __init__(
        self,
        company_id: str,
        company_name: str,
        previous_state: Mapping[str, Any] | None = None,
        now_provider: NowProvider | None = None,
    ) -> None:
        """Initialize one isolated company run from its prior snapshot."""

        if not company_id.strip():
            raise ValueError("company_id must be a non-empty string")
        if not company_name.strip():
            raise ValueError("company_name must be a non-empty string")

        self.company_id = company_id
        self.company_name = company_name
        self.previous_state = dict(previous_state or {})
        active_now_provider = now_provider or (
            lambda: datetime.now(timezone.utc)
        )
        self.run_at = active_now_provider()
        if self.run_at.tzinfo is None:
            raise ValueError("Health tracker timestamps must be timezone-aware")

        self.fetched_job_count = 0
        self.relevant_job_count = 0
        self.new_job_count = 0
        self.duplicate_job_count = 0
        self.title_rejection_count = 0
        self.location_rejection_count = 0
        self.error_type: str | None = None
        self._fetch_recorded = False

    def record_fetch(self, job_count: int) -> None:
        """Record the number of raw jobs returned by the adapter."""

        if (
            not isinstance(job_count, int)
            or isinstance(job_count, bool)
            or job_count < 0
        ):
            raise ValueError("job_count must be a non-negative integer")
        self.fetched_job_count = job_count
        self._fetch_recorded = True

    def record_relevant(self) -> None:
        """Record a job that passed title and location filtering."""

        self.relevant_job_count += 1

    def record_new(self) -> None:
        """Record a relevant job not present in history or pending state."""

        self.new_job_count += 1

    def record_duplicate(self) -> None:
        """Record a relevant job already known to durable or cycle state."""

        self.duplicate_job_count += 1

    def record_title_rejection(self) -> None:
        """Record a job rejected by deterministic title filtering."""

        self.title_rejection_count += 1

    def record_location_rejection(self) -> None:
        """Record a job rejected by either location filter."""

        self.location_rejection_count += 1

    def record_failure(self, error: BaseException | str) -> None:
        """Record one hard adapter failure for anomaly tracking."""

        if isinstance(error, BaseException):
            self.error_type = type(error).__name__
        else:
            error_type = error.strip()
            self.error_type = error_type or "UnknownError"

    def snapshot(self) -> dict[str, Any]:
        """Return the complete JSON-compatible state after this run."""

        previous_last_success = self.previous_state.get("last_success_at")
        last_success_at = (
            self.run_at.isoformat()
            if self.relevant_job_count > 0
            else previous_last_success
        )
        previous_failures = self._previous_non_negative_int(
            "consecutive_failures"
        )
        consecutive_failures = (
            previous_failures + 1 if self.error_type is not None else 0
        )
        previous_zero_runs = self._previous_non_negative_int(
            "consecutive_zero_job_runs"
        )
        if self.error_type is not None or not self._fetch_recorded:
            consecutive_zero_runs = previous_zero_runs
        elif self.fetched_job_count == 0:
            consecutive_zero_runs = previous_zero_runs + 1
        else:
            consecutive_zero_runs = 0

        job_count_history = self._updated_job_count_history()
        historical_average = (
            sum(job_count_history) / len(job_count_history)
            if job_count_history
            else 0.0
        )

        if last_success_at is None:
            last_status = "unverified"
        elif self.error_type is not None:
            last_status = "failed"
        elif (
            consecutive_zero_runs
            >= self.SILENT_BREAKAGE_RUN_THRESHOLD
        ):
            last_status = "degraded"
        else:
            last_status = "healthy"

        return {
            "company_name": self.company_name,
            "last_run_at": self.run_at.isoformat(),
            "last_success_at": last_success_at,
            "last_status": last_status,
            "consecutive_failures": consecutive_failures,
            "consecutive_zero_job_runs": consecutive_zero_runs,
            "last_job_count": self.fetched_job_count,
            "historical_avg_job_count": historical_average,
            "job_count_history": job_count_history,
            "last_error_type": self.error_type,
            "last_relevant_job_count": self.relevant_job_count,
            "last_new_job_count": self.new_job_count,
            "last_duplicate_job_count": self.duplicate_job_count,
            "last_title_rejection_count": self.title_rejection_count,
            "last_location_rejection_count": self.location_rejection_count,
        }

    def summary_line(self) -> str:
        """Return one muted, operator-focused terminal health line."""

        status = str(self.snapshot()["last_status"])
        prefixes = {
            "unverified": "⚠️ [UNVERIFIED]",
            "failed": "❌ [FAILED]",
            "degraded": "⚠️ [DEGRADED]",
            "healthy": "✅ [HEALTHY]",
        }
        return (
            f"{prefixes[status]} {self.company_name}: "
            f"{self.fetched_job_count} fetched | "
            f"{self.relevant_job_count} relevant | "
            f"{self.new_job_count} new | "
            f"{self.duplicate_job_count} duplicates | "
            f"{self.title_rejection_count} title rejected | "
            f"{self.location_rejection_count} location rejected"
        )

    def _updated_job_count_history(self) -> list[int]:
        """Append this successful fetch and retain only the latest 20."""

        raw_history = self.previous_state.get("job_count_history", [])
        history = (
            [
                count
                for count in raw_history
                if isinstance(count, int)
                and not isinstance(count, bool)
                and count >= 0
            ]
            if isinstance(raw_history, list)
            else []
        )
        if self._fetch_recorded and self.error_type is None:
            history.append(self.fetched_job_count)
        return history[-self.HISTORY_WINDOW_SIZE :]

    def _previous_non_negative_int(self, field_name: str) -> int:
        """Read one prior counter defensively."""

        value = self.previous_state.get(field_name, 0)
        if (
            isinstance(value, int)
            and not isinstance(value, bool)
            and value >= 0
        ):
            return value
        return 0
