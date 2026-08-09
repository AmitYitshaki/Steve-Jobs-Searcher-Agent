"""Tests for bounded HTTP scraping and explicit ATS failures."""

from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")

import scraper  # noqa: E402
from scrapers.browser import custom_adapters  # noqa: E402


class FetchAtsJobsTests(unittest.TestCase):
    """Verify the mapping-driven JSON ATS interface directly."""

    def test_get_mappings_normalize_jobs(self) -> None:
        """Normalize every GET-based ATS through one fetching interface."""

        cases = (
            (
                "greenhouse",
                {
                    "jobs": [
                        {
                            "id": 101,
                            "title": "Student Developer",
                            "location": {"name": "Tel Aviv, Israel"},
                            "absolute_url": "https://jobs.test/101",
                            "content": "<p>Build APIs.</p>",
                            "description": "Support production.",
                        }
                    ]
                },
                {
                    "id": "example_101",
                    "title": "Student Developer",
                    "location": "Tel Aviv, Israel",
                    "url": "https://jobs.test/101",
                    "content": "Build APIs.\nSupport production.",
                },
            ),
            (
                "amazon_jobs",
                {
                    "jobs": [
                        {
                            "id_ic": "A-102",
                            "title": "Software Engineer Intern",
                            "city": "Haifa",
                            "job_path": "/en/jobs/A-102",
                            "description": "Build services.",
                            "basic_qualifications": "Study CS.",
                            "preferred_qualifications": "Know Python.",
                        }
                    ]
                },
                {
                    "id": "example_A-102",
                    "title": "Software Engineer Intern",
                    "location": "Haifa",
                    "url": "https://www.amazon.jobs/en/jobs/A-102",
                    "content": (
                        "Build services.\nStudy CS.\nKnow Python."
                    ),
                },
            ),
            (
                "smartrecruiters",
                {
                    "content": [
                        {
                            "id": "SR-103",
                            "name": "Junior Data Analyst",
                            "location": {"city": "Jerusalem"},
                            "ref": "https://jobs.test/SR-103",
                            "jobAd": "Analyze data.",
                            "description": "Create reports.",
                        }
                    ]
                },
                {
                    "id": "example_SR-103",
                    "title": "Junior Data Analyst",
                    "location": "Jerusalem",
                    "url": "https://jobs.test/SR-103",
                    "content": "Analyze data.\nCreate reports.",
                },
            ),
            (
                "ashby",
                {
                    "jobs": [
                        {
                            "id": "ASH-104",
                            "title": "Student Backend Engineer",
                            "location": "Ramat Gan",
                            "jobUrl": "https://jobs.test/ASH-104",
                            "descriptionPlain": "Build backends.",
                            "descriptionHtml": "<p>Work in Python.</p>",
                            "description": "Learn quickly.",
                        }
                    ]
                },
                {
                    "id": "example_ASH-104",
                    "title": "Student Backend Engineer",
                    "location": "Ramat Gan",
                    "url": "https://jobs.test/ASH-104",
                    "content": (
                        "Build backends.\nWork in Python.\nLearn quickly."
                    ),
                },
            ),
        )

        for ats_type, payload, expected_job in cases:
            with self.subTest(ats_type=ats_type):
                response = MagicMock()
                response.json.return_value = payload
                company = self._company(ats_type)
                with patch(
                    "scraper.requests.get",
                    return_value=response,
                ) as get:
                    jobs = scraper.fetch_ats_jobs(
                        company,
                        scraper.ATS_FIELD_MAP[ats_type],
                    )

                self.assertEqual(jobs, [expected_job])
                get.assert_called_once_with(
                    "https://example.test/api",
                    timeout=15,
                )
                response.raise_for_status.assert_called_once_with()

    def test_workday_mapping_posts_payload_and_builds_job_url(self) -> None:
        """Use Workday's POST configuration and derived career base URL."""

        response = MagicMock()
        response.json.return_value = {
            "jobPostings": [
                {
                    "bulletinId": "WD-105",
                    "title": "Student Software Engineer",
                    "locationsText": "Israel",
                    "externalPath": "/job/WD-105",
                    "jobDescription": "Build software.",
                    "description": "Join the platform team.",
                }
            ]
        }
        company = {
            **self._company("workday"),
            "api_url": (
                "https://example.test/wday/cxs/example/jobs"
            ),
        }

        with patch(
            "scraper.requests.post",
            return_value=response,
        ) as post:
            jobs = scraper.fetch_ats_jobs(
                company,
                scraper.ATS_FIELD_MAP["workday"],
            )

        self.assertEqual(
            jobs,
            [
                {
                    "id": "example_WD-105",
                    "title": "Student Software Engineer",
                    "location": "Israel",
                    "url": "https://example.test/job/WD-105",
                    "content": (
                        "Build software.\nJoin the platform team."
                    ),
                }
            ],
        )
        post.assert_called_once_with(
            "https://example.test/wday/cxs/example/jobs",
            json={"limit": 20, "offset": 0, "appliedFacets": {}},
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=15,
        )

    def test_workday_mapping_handles_configured_http_status(self) -> None:
        """Return no jobs for Workday's configured auth error statuses."""

        response = MagicMock()
        response.status_code = 403
        error = scraper.requests.exceptions.HTTPError(response=response)
        response.raise_for_status.side_effect = error

        with (
            patch("scraper.requests.post", return_value=response),
            patch("builtins.print") as print_output,
        ):
            jobs = scraper.fetch_ats_jobs(
                self._company("workday"),
                scraper.ATS_FIELD_MAP["workday"],
            )

        self.assertEqual(jobs, [])
        self.assertIn("403", str(print_output.call_args))

    def test_greenhouse_eu_reuses_greenhouse_mapping(self) -> None:
        """Keep the EU ATS name as a true alias of Greenhouse rules."""

        self.assertIs(
            scraper.ATS_FIELD_MAP["greenhouse_eu"],
            scraper.ATS_FIELD_MAP["greenhouse"],
        )

    @staticmethod
    def _company(ats_type: str) -> dict[str, object]:
        """Return minimal company configuration for direct ATS fetching."""

        return {
            "company_id": "example",
            "company_name": "Example",
            "ats_type": ats_type,
            "api_url": "https://example.test/api",
        }


class CompanyRoutingValidationTests(unittest.TestCase):
    """Verify startup validation identifies active unroutable configs."""

    def test_valid_active_companies_have_no_routing_errors(self) -> None:
        """Accept JSON, direct, and browser-backed routing strategies."""

        companies = [
            {
                "company_id": "greenhouse-company",
                "ats_type": "greenhouse",
                "is_active": True,
            },
            {
                "company_id": "successfactors-company",
                "ats_type": "successfactors",
                "is_active": True,
            },
            {
                "company_id": "eightfold-company",
                "ats_type": "eightfold",
                "is_active": True,
            },
            {
                "company_id": "browser-company",
                "ats_type": "custom",
                "fetch_strategy": "browser",
                "is_active": True,
            },
        ]

        self.assertEqual(scraper.validate_company_routing(companies), [])

    def test_bad_active_config_returns_company_id(self) -> None:
        """Report active configs that have no available fetch route."""

        companies = [
            {
                "company_id": "unroutable-company",
                "ats_type": "unsupported",
                "is_active": True,
            }
        ]

        self.assertEqual(
            scraper.validate_company_routing(companies),
            ["unroutable-company"],
        )


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
            "scrapers.browser.custom_adapters.requests.get",
            return_value=response,
        ) as get:
            custom_adapters.scrape_successfactors(
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
                "scrapers.browser.custom_adapters.requests.get",
                return_value=response,
            ) as get,
            patch(
                "scrapers.browser.custom_adapters."
                "scrape_universal_playwright"
            ) as fallback,
        ):
            jobs = custom_adapters.scrape_eightfold(
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
                "scrapers.browser.custom_adapters.requests.get",
                side_effect=custom_adapters.requests.ConnectionError(
                    "API unavailable"
                ),
            ),
            patch(
                "scrapers.browser.custom_adapters."
                "scrape_universal_playwright",
                return_value=expected_jobs,
            ) as fallback,
        ):
            jobs = custom_adapters.scrape_eightfold(
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

        company = {
            **self._company("microsoft_custom"),
            "fetch_strategy": "browser",
        }
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
