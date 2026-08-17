"""Tests for isolated per-company scraper-health tracking."""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from scrapers.health import CompanyHealthTracker
from storage.drivers.atomic_json import AtomicJsonDictStore
from storage.health import ScraperHealthStore


class AtomicJsonDictStoreTests(unittest.TestCase):
    """Verify atomic JSON-object persistence."""

    def test_round_trips_json_mapping(self) -> None:
        """Persist scraper-health state as one top-level JSON object."""

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scraper_health.json"
            store = AtomicJsonDictStore(path)

            store.write({"example": {"last_status": "unverified"}})

            self.assertEqual(
                store.read(),
                {"example": {"last_status": "unverified"}},
            )

    def test_rejects_non_mapping_json(self) -> None:
        """Fail loudly when health state is not a top-level object."""

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scraper_health.json"
            path.write_text("[]", encoding="utf-8")

            with self.assertRaises(ValueError):
                AtomicJsonDictStore(path).read()

    def test_rejects_non_mapping_write(self) -> None:
        """Validate the dictionary-store boundary before file mutation."""

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scraper_health.json"

            with self.assertRaises(ValueError):
                AtomicJsonDictStore(path).write([])  # type: ignore[arg-type]

            self.assertFalse(path.exists())

    def test_reuses_windows_lock_retry_behavior(self) -> None:
        """Retry atomic dictionary replacement after access-denied locks."""

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scraper_health.json"
            real_replace = os.replace
            sleep_function = MagicMock()
            store = AtomicJsonDictStore(
                path,
                sleep_function=sleep_function,
            )
            attempts = 0

            def replace_after_one_lock(
                source: str | Path,
                destination: str | Path,
            ) -> None:
                """Simulate one Windows lock before replacement succeeds."""

                nonlocal attempts
                attempts += 1
                if attempts == 1:
                    raise PermissionError(5, "Access is denied")
                real_replace(source, destination)

            with patch(
                "storage.drivers.atomic_json.os.replace",
                side_effect=replace_after_one_lock,
            ):
                store.write({"example": {}})

            self.assertEqual(store.read(), {"example": {}})
            sleep_function.assert_called_once_with(0.1)


class ScraperHealthStoreTests(unittest.TestCase):
    """Verify isolated health-state persistence."""

    def test_round_trips_per_company_health_state(self) -> None:
        """Persist company records without mixing them into other stores."""

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scraper_health.json"
            store = ScraperHealthStore(path)
            state = {
                "example": {
                    "last_status": "unverified",
                    "last_success_at": None,
                }
            }

            store.save(state)

            self.assertEqual(store.load(), state)


class CompanyHealthTrackerTests(unittest.TestCase):
    """Verify per-company health calculations and operator summaries."""

    NOW = datetime(2026, 8, 17, 9, 30, tzinfo=timezone.utc)

    def test_never_verified_scraper_is_prominently_flagged(self) -> None:
        """Keep zero-result adapters unverified until relevance is proven."""

        tracker = CompanyHealthTracker(
            company_id="example",
            company_name="CompanyX",
            previous_state={},
            now_provider=lambda: self.NOW,
        )

        tracker.record_fetch(0)
        state = tracker.snapshot()

        self.assertIsNone(state["last_success_at"])
        self.assertEqual(state["last_status"], "unverified")
        self.assertTrue(
            tracker.summary_line().startswith(
                "⚠️ [UNVERIFIED] CompanyX: 0 fetched |"
            )
        )

    def test_historical_average_uses_latest_twenty_runs(self) -> None:
        """Discard older counts when calculating the rolling baseline."""

        state: dict[str, object] = {}
        for job_count in range(1, 26):
            tracker = CompanyHealthTracker(
                company_id="example",
                company_name="CompanyX",
                previous_state=state,
                now_provider=lambda: self.NOW,
            )
            tracker.record_fetch(job_count)
            state = tracker.snapshot()

        self.assertEqual(state["job_count_history"], list(range(6, 26)))
        self.assertEqual(state["historical_avg_job_count"], 15.5)

    def test_relevant_duplicate_proves_scraper_and_is_visible(self) -> None:
        """Count known relevant jobs without misreporting them as new."""

        tracker = CompanyHealthTracker(
            company_id="example",
            company_name="CompanyX",
            previous_state={},
            now_provider=lambda: self.NOW,
        )

        tracker.record_fetch(3)
        tracker.record_relevant()
        tracker.record_duplicate()
        state = tracker.snapshot()

        self.assertEqual(
            state["last_success_at"],
            "2026-08-17T09:30:00+00:00",
        )
        self.assertEqual(state["last_status"], "healthy")
        self.assertEqual(state["last_duplicate_job_count"], 1)
        self.assertIn("1 duplicates", tracker.summary_line())

    def test_unverified_status_overrides_hard_failure(self) -> None:
        """Keep never-proven adapters visible even when a fetch raises."""

        tracker = CompanyHealthTracker(
            company_id="example",
            company_name="CompanyX",
            previous_state={},
            now_provider=lambda: self.NOW,
        )

        tracker.record_failure(TimeoutError("timed out"))
        state = tracker.snapshot()

        self.assertEqual(state["last_status"], "unverified")
        self.assertEqual(state["last_error_type"], "TimeoutError")
        self.assertEqual(state["consecutive_failures"], 1)

    def test_zero_run_degradation_survives_rolling_window(self) -> None:
        """Keep silent breakage degraded after the positive count ages out."""

        verified = CompanyHealthTracker(
            company_id="example",
            company_name="CompanyX",
            previous_state={},
            now_provider=lambda: self.NOW,
        )
        verified.record_fetch(10)
        verified.record_relevant()
        state = verified.snapshot()

        for _ in range(20):
            tracker = CompanyHealthTracker(
                company_id="example",
                company_name="CompanyX",
                previous_state=state,
                now_provider=lambda: self.NOW,
            )
            tracker.record_fetch(0)
            state = tracker.snapshot()

        self.assertEqual(state["consecutive_zero_job_runs"], 20)
        self.assertEqual(state["historical_avg_job_count"], 0.0)
        self.assertEqual(state["last_status"], "degraded")


if __name__ == "__main__":
    unittest.main()
