"""Durable local storage for pending alerts and delivered job IDs."""

from __future__ import annotations

import json
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

SleepFunction = Callable[[float], None]


@dataclass(frozen=True)
class PendingAlert:
    """Represent one analyzed job waiting for Telegram delivery."""

    job_id: str
    company_name: str
    job_url: str
    llm_summary: str

    def __post_init__(self) -> None:
        """Reject incomplete records before they reach persistent storage."""

        for field_name in (
            "job_id",
            "company_name",
            "job_url",
            "llm_summary",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")

    def to_dict(self) -> dict[str, str]:
        """Return the JSON-compatible representation of this alert."""

        return {
            "job_id": self.job_id,
            "company_name": self.company_name,
            "job_url": self.job_url,
            "llm_summary": self.llm_summary,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> PendingAlert:
        """Create a validated alert from a decoded JSON object."""

        try:
            return cls(
                job_id=value["job_id"],
                company_name=value["company_name"],
                job_url=value["job_url"],
                llm_summary=value["llm_summary"],
            )
        except KeyError as error:
            raise ValueError(
                f"Pending alert is missing {error.args[0]}"
            ) from error


class AtomicJsonListStore:
    """Read and atomically replace a JSON file containing a list."""

    def __init__(
        self,
        path: str | Path,
        replace_attempts: int = 5,
        initial_retry_delay_seconds: float = 0.1,
        max_retry_delay_seconds: float = 0.5,
        sleep_function: SleepFunction = time.sleep,
    ) -> None:
        """Configure atomic storage and bounded Windows lock retries."""

        if replace_attempts < 1:
            raise ValueError("replace_attempts must be at least 1")
        if initial_retry_delay_seconds < 0:
            raise ValueError(
                "initial_retry_delay_seconds cannot be negative"
            )
        if max_retry_delay_seconds < initial_retry_delay_seconds:
            raise ValueError(
                "max_retry_delay_seconds cannot be below the initial delay"
            )
        self.path = Path(path)
        self.replace_attempts = replace_attempts
        self.initial_retry_delay_seconds = initial_retry_delay_seconds
        self.max_retry_delay_seconds = max_retry_delay_seconds
        self.sleep_function = sleep_function

    def read(self) -> list[Any]:
        """Return the stored list, or an empty list when no file exists."""

        if not self.path.exists():
            return []

        with open(self.path, "r", encoding="utf-8") as handle:
            value = json.load(handle)
        if not isinstance(value, list):
            raise ValueError(f"{self.path} must contain a JSON list")
        return value

    def write(self, value: list[Any]) -> None:
        """Write a closed temporary file, then atomically replace the target."""

        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            file_descriptor, temporary_name = tempfile.mkstemp(
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
            )
            os.close(file_descriptor)
            temporary_path = Path(temporary_name)

            with open(temporary_path, "w", encoding="utf-8") as handle:
                json.dump(
                    value,
                    handle,
                    ensure_ascii=False,
                    indent=2,
                )
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())

            # The temporary-file handle is closed before Windows is asked to
            # replace the destination.
            self._replace_with_retry(temporary_path)
        finally:
            if temporary_path is not None and temporary_path.exists():
                try:
                    temporary_path.unlink()
                except OSError:
                    pass

    def _replace_with_retry(self, temporary_path: Path) -> None:
        """Retry transient Windows access-denied errors during replacement."""

        for attempt in range(1, self.replace_attempts + 1):
            try:
                os.replace(temporary_path, self.path)
                return
            except OSError as error:
                is_windows_lock = (
                    isinstance(error, PermissionError)
                    or getattr(error, "winerror", None) == 5
                )
                if not is_windows_lock or attempt >= self.replace_attempts:
                    raise

                delay = min(
                    self.initial_retry_delay_seconds * attempt,
                    self.max_retry_delay_seconds,
                )
                self.sleep_function(delay)


class PendingAlertQueue:
    """Persist pending alerts with job-ID deduplication."""

    def __init__(self, path: str | Path = "pending_alerts.json") -> None:
        """Initialize a queue backed by one local JSON file."""

        self.store = AtomicJsonListStore(path)

    def load(self) -> list[PendingAlert]:
        """Load and validate every pending alert."""

        alerts: list[PendingAlert] = []
        for value in self.store.read():
            if not isinstance(value, dict):
                raise ValueError("Every pending alert must be a JSON object")
            alerts.append(PendingAlert.from_mapping(value))
        return alerts

    def ids(self) -> set[str]:
        """Return all job IDs currently waiting for delivery."""

        return {alert.job_id for alert in self.load()}

    def append(self, alert: PendingAlert) -> bool:
        """Append an alert atomically unless its job ID is already queued."""

        alerts = self.load()
        if any(existing.job_id == alert.job_id for existing in alerts):
            return False
        alerts.append(alert)
        self.store.write([value.to_dict() for value in alerts])
        return True

    def remove(self, job_id: str) -> bool:
        """Remove one job atomically while preserving all other alerts."""

        alerts = self.load()
        remaining = [
            alert for alert in alerts if alert.job_id != job_id
        ]
        if len(remaining) == len(alerts):
            return False
        self.store.write([value.to_dict() for value in remaining])
        return True


class JobHistoryStore:
    """Persist the IDs of jobs whose alerts were delivered."""

    def __init__(self, path: str | Path = "jobs_history.json") -> None:
        """Initialize a history store backed by one local JSON file."""

        self.store = AtomicJsonListStore(path)

    def load(self) -> set[str]:
        """Load delivered job IDs and validate their types."""

        values = self.store.read()
        if not all(isinstance(value, str) for value in values):
            raise ValueError("Job history entries must be strings")
        return set(values)

    def contains(self, job_id: str) -> bool:
        """Return whether a job was already delivered."""

        return job_id in self.load()

    def add(self, job_id: str) -> bool:
        """Atomically add a delivered job ID if it is not present."""

        if not isinstance(job_id, str) or not job_id.strip():
            raise ValueError("job_id must be a non-empty string")

        job_ids = self.load()
        if job_id in job_ids:
            return False
        job_ids.add(job_id)
        self.store.write(sorted(job_ids))
        return True
