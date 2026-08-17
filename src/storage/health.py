"""Durable isolated state for per-company scraper health."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from paths import DATA_DIR
from storage.drivers.atomic_json import AtomicJsonDictStore


class ScraperHealthStore:
    """Persist validated health records independently of job state."""

    def __init__(
        self,
        path: str | Path = DATA_DIR / "scraper_health.json",
    ) -> None:
        """Initialize a health store backed by one local JSON object."""

        self.store = AtomicJsonDictStore(path)

    def load(self) -> dict[str, dict[str, Any]]:
        """Load and validate all per-company health records."""

        return self._validate_state(self.store.read())

    def save(
        self,
        state: Mapping[str, Mapping[str, Any]],
    ) -> None:
        """Validate and atomically replace the complete health state."""

        self.store.write(self._validate_state(state))

    @staticmethod
    def _validate_state(
        state: Mapping[str, Any],
    ) -> dict[str, dict[str, Any]]:
        """Return plain dictionaries for valid company health records."""

        validated: dict[str, dict[str, Any]] = {}
        for company_id, record in state.items():
            if not isinstance(company_id, str) or not company_id.strip():
                raise ValueError(
                    "Scraper health company IDs must be non-empty strings"
                )
            if not isinstance(record, Mapping):
                raise ValueError(
                    "Every scraper health record must be a JSON object"
                )
            validated[company_id] = dict(record)
        return validated
