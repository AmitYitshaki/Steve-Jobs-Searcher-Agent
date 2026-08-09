"""Tests for geographic leak prevention."""

from __future__ import annotations

import unittest

from analysis.filters.location import LocationFilter


class LocationFilterTests(unittest.TestCase):
    """Verify safe blacklist matching and optional whitelist behavior."""

    def setUp(self) -> None:
        """Create the default blacklist-based filter."""

        self.location_filter = LocationFilter()

    def test_rejects_blocked_city_in_title(self) -> None:
        """Reject a foreign Similar Jobs title."""

        decision = self.location_filter.evaluate(
            job_title="Student Software Engineer - Budapest, Hungary",
            job_url="https://example.test/jobs/123",
        )

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.matched_location, "Budapest")
        self.assertEqual(decision.source, "title")

    def test_rejects_url_encoded_foreign_location(self) -> None:
        """Detect foreign cities and countries inside encoded URLs."""

        decision = self.location_filter.evaluate(
            job_title="Junior Data Analyst",
            job_url=(
                "https://example.test/jobs/"
                "Santiago%2C-Chile/junior-data-analyst"
            ),
        )

        self.assertFalse(decision.allowed)
        self.assertIn(
            decision.matched_location,
            {"Santiago", "Chile"},
        )
        self.assertEqual(decision.source, "url")

    def test_rejects_uppercase_us_location_code(self) -> None:
        """Treat standalone uppercase US as a location marker."""

        decision = self.location_filter.evaluate(
            job_title="Software Engineer Intern - Remote - US",
            job_url="https://example.test/jobs/123",
        )

        self.assertFalse(decision.allowed)

    def test_does_not_match_lowercase_us_pronoun(self) -> None:
        """Avoid ordinary 'us', join-us paths, and en-US locale settings."""

        decision = self.location_filter.evaluate(
            job_title="Join us as a Junior Software Engineer",
            job_url=(
                "https://example.test/join-us/jobs/123"
                "?locale=en-US"
            ),
        )

        self.assertTrue(decision.allowed)

    def test_rejects_us_url_path_segment(self) -> None:
        """Reject US when it is a complete geographic URL segment."""

        decision = self.location_filter.evaluate(
            job_title="Junior Software Engineer",
            job_url="https://example.test/jobs/us/123",
        )

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.matched_location, "US")
        self.assertEqual(decision.source, "url")

    def test_rejects_philippines_locations(self) -> None:
        """Reject Philippine country, city, and URL-code variants."""

        cases = (
            (
                "Junior QA Engineer - Philippines",
                "https://example.test/jobs/123",
                "Philippines",
            ),
            (
                "Junior QA Engineer - Manila",
                "https://example.test/jobs/456",
                "Manila",
            ),
            (
                "Junior QA Engineer",
                "https://example.test/jobs/ph/789",
                "PH",
            ),
        )
        for title, url, expected_location in cases:
            with self.subTest(location=expected_location):
                decision = self.location_filter.evaluate(title, url)
                self.assertFalse(decision.allowed)
                self.assertEqual(
                    decision.matched_location,
                    expected_location,
                )

    def test_uses_word_boundaries_for_country_names(self) -> None:
        """Avoid matching a blocked location inside a larger word."""

        decision = self.location_filter.evaluate(
            job_title="Junior Industrial Automation Engineer",
            job_url="https://example.test/jobs/industrial/123",
        )

        self.assertTrue(decision.allowed)

    def test_blocked_location_wins_over_allowed_url(self) -> None:
        """Reject a foreign title even when the parent URL mentions Israel."""

        decision = self.location_filter.evaluate(
            job_title="Student Developer - London",
            job_url="https://example.test/careers/israel/similar/123",
        )

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.matched_location, "London")

    def test_strict_mode_accepts_known_israeli_location(self) -> None:
        """Allow an Israeli location when whitelist mode is enabled."""

        decision = LocationFilter(strict_mode=True).evaluate(
            job_title="Junior Backend Developer - Tel Aviv",
            job_url="https://example.test/jobs/123",
        )

        self.assertTrue(decision.allowed)

    def test_strict_mode_accepts_new_israeli_locations(self) -> None:
        """Allow every newly configured Israeli city and district."""

        strict_filter = LocationFilter(strict_mode=True)
        for location in (
            "Ramat Hahayal",
            "Yavne",
            "Rehovot",
            "Lod",
            "Modiin",
        ):
            with self.subTest(location=location):
                decision = strict_filter.evaluate(
                    job_title=f"Student Developer - {location}",
                    job_url="https://example.test/jobs/123",
                )
                self.assertTrue(decision.allowed)

    def test_strict_mode_rejects_unknown_location(self) -> None:
        """Reject jobs with no recognized Israeli location in strict mode."""

        decision = LocationFilter(strict_mode=True).evaluate(
            job_title="Junior Backend Developer",
            job_url="https://example.test/jobs/123",
        )

        self.assertFalse(decision.allowed)
        self.assertIn("strict mode", decision.reason)


if __name__ == "__main__":
    unittest.main()
