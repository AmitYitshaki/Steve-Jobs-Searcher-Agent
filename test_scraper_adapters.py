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

    def test_unknown_ats_emits_logging_warning(self) -> None:
        """Make unsupported ATS types visible through standard logging."""

        with (
            patch("scraper.logging.warning") as warning,
            patch("builtins.print"),
        ):
            jobs = scraper.fetch_jobs_from_company(
                self._company("eightfold")
            )

        self.assertEqual(jobs, [])
        warning.assert_called_once()
        self.assertIn(
            "No adapter available",
            warning.call_args.args[0],
        )
        self.assertIn("eightfold", warning.call_args.args)

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
