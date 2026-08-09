"""Durable storage for delivered job identifiers."""

from __future__ import annotations

from pathlib import Path

from paths import DATA_DIR
from storage.drivers.atomic_json import AtomicJsonListStore


class JobHistoryStore:
    """Persist the IDs of jobs whose alerts were delivered."""

    def __init__(
        self,
        path: str | Path = DATA_DIR / "jobs_history.json",
    ) -> None:
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
