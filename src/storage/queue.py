"""Durable pending-alert records and queue storage."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from paths import DATA_DIR
from storage.drivers.atomic_json import AtomicJsonListStore


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


class PendingAlertQueue:
    """Persist pending alerts with job-ID deduplication."""

    def __init__(
        self,
        path: str | Path = DATA_DIR / "pending_alerts.json",
    ) -> None:
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
