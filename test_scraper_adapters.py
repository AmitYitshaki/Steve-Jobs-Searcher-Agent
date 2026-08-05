"""Tests for bounded HTTP scraping and explicit ATS failures."""

from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")

import html_adapters  # noqa: E402
import scraper  # noqa: E402


class ScraperAdapterTests(unittest.TestCase):
    """Verify adapter transport bounds and factual content extraction."""

    def test_greenhouse_extracts_actual_content_with_timeout(self) -> None:
        """Read Greenhouse content instead of synthesizing a description."""

        response = MagicMock()
        response.json.return_value = {
            "jobs": [
                {
                    "id": 123,
                    "title": "Student Developer - Israel",
                    "location": {"name": "Tel Aviv, Israel"},
                    "absolute_url": (
                        "https://example.test/jobs/israel/123"
                    ),
                    "content": (
                        "<p>Build Python services.</p>"
                        "<p>Requires two semesters.</p>"
                    ),
                }
            ]
        }
        with (
            patch("scraper.requests.get", return_value=response) as get,
            patch("builtins.print"),
        ):
            jobs = scraper.fetch_jobs_from_company(
                self._company("greenhouse")
            )

        get.assert_called_once_with(
            "https://example.test/api",
            timeout=15,
        )
        self.assertEqual(jobs[0]["url"], (
            "https://example.test/jobs/israel/123"
        ))
        self.assertIn("Build Python services.", jobs[0]["content"])
        self.assertNotIn("description", jobs[0])
        self.assertNotIn(
            "Full job description available at:",
            jobs[0]["content"],
        )

    def test_every_requests_ats_uses_fifteen_second_timeout(self) -> None:
        """Bound Workday, Amazon, SmartRecruiters, and Ashby requests."""

        response = MagicMock()
        response.json.return_value = {}

        with (
            patch(
                "scraper.requests.post",
                return_value=response,
            ) as post,
            patch("builtins.print"),
        ):
            scraper.fetch_jobs_from_company(self._company("workday"))
        self.assertEqual(post.call_args.kwargs["timeout"], 15)

        for ats_type in ("amazon_jobs", "smartrecruiters", "ashby"):
            with self.subTest(ats_type=ats_type):
                with (
                    patch(
                        "scraper.requests.get",
                        return_value=response,
                    ) as get,
                    patch("builtins.print"),
                ):
                    scraper.fetch_jobs_from_company(
                        self._company(ats_type)
                    )
                self.assertEqual(get.call_args.kwargs["timeout"], 15)

    def test_successfactors_request_uses_timeout(self) -> None:
        """Bound the HTML adapter request."""

        response = MagicMock()
        response.text = "<html></html>"
        with patch(
            "html_adapters.requests.get",
            return_value=response,
        ) as get:
            html_adapters.scrape_successfactors(
                self._company("successfactors")
            )

        self.assertEqual(get.call_args.kwargs["timeout"], 15)

    def test_eightfold_extracts_native_jobs_with_timeout(self) -> None:
        """Normalize a native Eightfold response without using Playwright."""

        response = MagicMock()
        response.json.return_value = {
            "data": {
                "positions": [
                    {
                        "id": 123,
                        "name": "Student Software Engineer",
                        "location": {
                            "city": "Tel Aviv",
                            "country": "Israel",
                        },
                        "canonicalPositionUrl": "/careers/job/123",
                        "description": (
                            "<p>Build cloud security services.</p>"
                        ),
                    }
                ]
            }
        }
        career_url = (
            "https://example.eightfold.ai/careers?query=israel"
        )
        with (
            patch(
                "html_adapters.requests.get",
                return_value=response,
            ) as get,
            patch(
                "html_adapters.scrape_universal_playwright"
            ) as fallback,
        ):
            jobs = html_adapters.scrape_eightfold(
                "palo_alto_networks",
                career_url,
            )

        self.assertEqual(
            get.call_args.args[0],
            "https://example.eightfold.ai/api/apply/v2/jobs",
        )
        self.assertEqual(get.call_args.kwargs["timeout"], 15)
        fallback.assert_not_called()
        self.assertEqual(jobs[0]["id"], "palo_alto_networks_123")
        self.assertEqual(jobs[0]["location"], "Tel Aviv, Israel")
        self.assertEqual(
            jobs[0]["url"],
            "https://example.eightfold.ai/careers/job/123",
        )
        self.assertEqual(
            jobs[0]["content"],
            "Build cloud security services.",
        )

    def test_eightfold_falls_back_to_universal_playwright(self) -> None:
        """Use the original career page when the native API is unavailable."""

        expected_jobs = [{"id": "palo_alto_networks_123"}]
        career_url = "https://jobs.paloaltonetworks.com/en/search-jobs"
        with (
            patch(
                "html_adapters.requests.get",
                side_effect=html_adapters.requests.ConnectionError(
                    "API unavailable"
                ),
            ),
            patch(
                "html_adapters.scrape_universal_playwright",
                return_value=expected_jobs,
            ) as fallback,
        ):
            jobs = html_adapters.scrape_eightfold(
                "palo_alto_networks",
                career_url,
            )

        self.assertEqual(jobs, expected_jobs)
        fallback.assert_called_once_with(
            {
                "company_id": "palo_alto_networks",
                "api_url": career_url,
            }
        )

    def test_eightfold_ats_routes_to_adapter(self) -> None:
        """Route Eightfold companies instead of reporting them unsupported."""

        company = self._company("eightfold")
        with (
            patch(
                "scraper.scrape_eightfold",
                return_value=[{"id": "example_123"}],
            ) as eightfold,
            patch("builtins.print"),
        ):
            jobs = scraper.fetch_jobs_from_company(company)

        self.assertEqual(jobs, [{"id": "example_123"}])
        eightfold.assert_called_once_with(
            "example",
            "https://example.test/api",
        )

    def test_microsoft_ats_routes_to_universal_playwright(self) -> None:
        """Route Microsoft through the universal Playwright adapter."""

        company = self._company("microsoft_custom")
        expected_jobs = [{"id": "example_123"}]
        with (
            patch(
                "scraper.scrape_universal_playwright",
                return_value=expected_jobs,
            ) as universal_playwright,
            patch("builtins.print"),
        ):
            jobs = scraper.fetch_jobs_from_company(company)

        self.assertEqual(jobs, expected_jobs)
        universal_playwright.assert_called_once_with(company)

    def test_unknown_ats_emits_logging_warning(self) -> None:
        """Make unsupported ATS types visible through standard logging."""

        with (
            patch("scraper.logging.warning") as warning,
            patch("builtins.print"),
        ):
            jobs = scraper.fetch_jobs_from_company(
                self._company("unsupported")
            )

        self.assertEqual(jobs, [])
        warning.assert_called_once()
        self.assertIn(
            "No adapter available",
            warning.call_args.args[0],
        )
        self.assertIn("unsupported", warning.call_args.args)

    @staticmethod
    def _company(ats_type: str) -> dict[str, object]:
        """Return a minimal company configuration for one adapter."""

        return {
            "company_id": "example",
            "company_name": "Example",
            "ats_type": ats_type,
            "api_url": "https://example.test/api",
        }


if __name__ == "__main__":
    unittest.main()
