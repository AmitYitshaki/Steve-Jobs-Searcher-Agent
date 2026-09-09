"""Tests for bounded HTTP scraping and explicit ATS failures."""

from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, call, patch

os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")

from models.results import ScrapeResult, ScrapeStatus  # noqa: E402
from scrapers import orchestrator as scraper  # noqa: E402
from scrapers.api import client as api_client  # noqa: E402
from scrapers.browser import custom_adapters  # noqa: E402


class FetchAtsJobsTests(unittest.TestCase):
    """Verify the mapping-driven JSON ATS interface directly."""

    def test_lever_mapping_normalizes_array_payload(self) -> None:
        """Normalize Lever's raw posting array without an envelope."""

        response = MagicMock()
        response.json.return_value = [
            {
                "id": "lever-123",
                "text": "Graduate Software Dev Engineer",
                "categories": {"location": "Jerusalem, Israel"},
                "hostedUrl": (
                    "https://jobs.eu.lever.co/mobileye/lever-123"
                ),
                "descriptionPlain": "Build autonomous-driving software.",
                "additionalPlain": "Work with perception teams.",
                "lists": [
                    {
                        "text": "Requirements",
                        "content": "B.Sc. in Computer Science.",
                    }
                ],
            }
        ]
        company = {
            "company_id": "mobileye",
            "company_name": "Mobileye",
            "ats_type": "lever",
            "api_url": (
                "https://api.eu.lever.co/v0/postings/"
                "mobileye?mode=json"
            ),
        }

        with patch(
            "scrapers.api.client.requests.get",
            return_value=response,
        ) as get:
            jobs = scraper.fetch_ats_jobs(
                company,
                scraper.ATS_FIELD_MAP["lever"],
            )

        self.assertIsNone(scraper.ATS_FIELD_MAP["lever"].envelope_key)
        self.assertEqual(
            jobs,
            [
                {
                    "id": "mobileye_lever-123",
                    "title": "Graduate Software Dev Engineer",
                    "location": "Jerusalem, Israel",
                    "url": (
                        "https://jobs.eu.lever.co/mobileye/lever-123"
                    ),
                    "content": (
                        "Build autonomous-driving software.\n"
                        "Work with perception teams.\n"
                        "Requirements\n"
                        "B.Sc. in Computer Science."
                    ),
                }
            ],
        )
        get.assert_called_once_with(
            company["api_url"],
            headers=api_client.DEFAULT_REQUEST_HEADERS,
            timeout=15,
        )

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
                    "scrapers.api.client.requests.get",
                    return_value=response,
                ) as get:
                    jobs = scraper.fetch_ats_jobs(
                        company,
                        scraper.ATS_FIELD_MAP[ats_type],
                    )

                self.assertEqual(jobs, [expected_job])
                get.assert_called_once_with(
                    "https://example.test/api",
                    headers=api_client.DEFAULT_REQUEST_HEADERS,
                    timeout=15,
                )
                response.raise_for_status.assert_called_once_with()

    def test_workday_mapping_posts_payload_and_builds_job_url(self) -> None:
        """Use Workday's POST configuration and derived career base URL."""

        response = MagicMock()
        response.json.return_value = {
            "total": 1,
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

        with (
            patch(
                "scrapers.api.client.requests.post",
                return_value=response,
            ) as post,
            patch("builtins.print"),
        ):
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
        self.assertEqual(post.call_count, 2)
        self.assertEqual(
            post.call_args_list[0].kwargs["json"],
            {
                "limit": 1,
                "offset": 0,
                "appliedFacets": {},
                "searchText": "",
            },
        )
        actual_call = post.call_args_list[1]
        self.assertEqual(
            actual_call.args,
            ("https://example.test/wday/cxs/example/jobs",),
        )
        self.assertEqual(
            actual_call.kwargs,
            {
                "json": {
                    "limit": 20,
                    "offset": 0,
                    "appliedFacets": {},
                    "searchText": "Israel",
                },
                "headers": {
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/152.0.0.0 Safari/537.36"
                    ),
                },
                "timeout": 15,
            },
        )

    def test_workday_mapping_fetches_every_israel_page(self) -> None:
        """Request successive Workday offsets until all matches are read."""

        first_page_jobs = [
            {
                "bulletinId": f"WD-{index}",
                "title": f"Israel Software Role {index}",
                "locationsText": "Israel",
                "externalPath": f"/job/WD-{index}",
            }
            for index in range(20)
        ]
        last_job = {
            "bulletinId": "WD-20",
            "title": "Israel Software Role 20",
            "locationsText": "Israel",
            "externalPath": "/job/WD-20",
        }
        first_response = MagicMock()
        first_response.json.return_value = {
            "total": 21,
            "jobPostings": first_page_jobs,
        }
        second_response = MagicMock()
        second_response.json.return_value = {
            "total": 21,
            "jobPostings": [last_job],
        }
        discovery_response = MagicMock()
        discovery_response.json.return_value = {
            "total": 2000,
            "jobPostings": [],
            "facets": [],
        }
        company = {
            **self._company("workday"),
            "api_url": "https://example.test/wday/cxs/example/jobs",
        }

        with (
            patch(
                "scrapers.api.client.requests.post",
                side_effect=[
                    discovery_response,
                    first_response,
                    second_response,
                ],
            ) as post,
            patch("builtins.print"),
        ):
            jobs = scraper.fetch_ats_jobs(
                company,
                scraper.ATS_FIELD_MAP["workday"],
            )

        self.assertEqual(len(jobs), 21)
        self.assertEqual(jobs[-1]["id"], "example_WD-20")
        self.assertEqual(post.call_count, 3)
        self.assertEqual(
            post.call_args_list[0].kwargs["json"]["searchText"],
            "",
        )
        self.assertEqual(
            [
                call.kwargs["json"]["offset"]
                for call in post.call_args_list[1:]
            ],
            [0, 20],
        )
        self.assertTrue(
            all(
                call.kwargs["json"]["searchText"] == "Israel"
                for call in post.call_args_list[1:]
            )
        )

    def test_workday_discovers_and_applies_israel_location_facet(self) -> None:
        """Prefer a real Workday location facet over full-text matching."""

        discovery_response = MagicMock()
        discovery_response.json.return_value = {
            "total": 2000,
            "jobPostings": [
                {
                    "bulletinId": "GLOBAL-1",
                    "title": "Global Role",
                    "locationsText": "Bangalore, India",
                    "externalPath": "/job/GLOBAL-1",
                }
            ],
            "facets": [
                {
                    "facetParameter": "locationMainGroup",
                    "values": [
                        {
                            "facetParameter": "locationHierarchy1",
                            "descriptor": "Locations",
                            "values": [
                                {
                                    "descriptor": "Israel",
                                    "id": "israel-facet-id",
                                    "count": 21,
                                },
                                {
                                    "descriptor": "India",
                                    "id": "india-facet-id",
                                    "count": 500,
                                },
                            ],
                        }
                    ],
                }
            ],
        }
        scoped_response = MagicMock()
        scoped_response.json.return_value = {
            "total": 1,
            "jobPostings": [
                {
                    "bulletinId": "IL-1",
                    "title": "Student Software Engineer",
                    "locationsText": "2 Locations",
                    "externalPath": "/job/IL-1",
                }
            ],
        }
        company = {
            **self._company("workday"),
            "api_url": "https://example.test/wday/cxs/example/jobs",
        }

        with patch(
            "scrapers.api.client.requests.post",
            side_effect=[discovery_response, scoped_response],
        ) as post:
            jobs = scraper.fetch_ats_jobs(
                company,
                scraper.ATS_FIELD_MAP["workday"],
            )

        self.assertEqual([job["id"] for job in jobs], ["example_IL-1"])
        self.assertEqual(jobs[0]["location"], "Israel\n2 Locations")
        self.assertEqual(post.call_count, 2)
        discovery_payload = post.call_args_list[0].kwargs["json"]
        self.assertEqual(discovery_payload["searchText"], "")
        self.assertEqual(discovery_payload["limit"], 1)
        scoped_payload = post.call_args_list[1].kwargs["json"]
        self.assertEqual(scoped_payload["searchText"], "")
        self.assertEqual(
            scoped_payload["appliedFacets"],
            {"locationHierarchy1": ["israel-facet-id"]},
        )

    def test_workday_scope_supports_country_and_city_facet_names(self) -> None:
        """Handle Workday tenant-specific location parameter conventions."""

        scope_fn = scraper.ATS_FIELD_MAP["workday"].scope_payload_fn
        self.assertIsNotNone(scope_fn)
        cases = [
            (
                {
                    "facets": [
                        {
                            "facetParameter": "Country",
                            "values": [
                                {
                                    "descriptor": "Israel",
                                    "id": "country-israel-id",
                                }
                            ],
                        }
                    ]
                },
                ["Israel", "Migdal HaEmek"],
                {"Country": ["country-israel-id"]},
            ),
            (
                {
                    "facets": [
                        {
                            "facetParameter": "locations",
                            "values": [
                                {
                                    "descriptor": "Rehovot,ISR",
                                    "id": "rehovot-id",
                                },
                                {
                                    "descriptor": "Bangalore,IND",
                                    "id": "bangalore-id",
                                },
                            ],
                        }
                    ]
                },
                ["Israel", "Rehovot"],
                {"locations": ["rehovot-id"]},
            ),
            (
                {
                    "facets": [
                        {
                            "facetParameter": "Location",
                            "values": [
                                {
                                    "descriptor": "Yokneam",
                                    "id": "yokneam-id",
                                },
                                {
                                    "descriptor": "IL - Petah Tikva",
                                    "id": "petah-tikva-id",
                                },
                            ],
                        }
                    ]
                },
                ["Israel", "Petah Tikva", "Yokneam"],
                {"Location": ["yokneam-id", "petah-tikva-id"]},
            ),
        ]

        for payload, location_filters, expected_facets in cases:
            with self.subTest(expected_facets=expected_facets):
                scope = scope_fn(
                    payload,
                    {"location_filters": location_filters},
                )
                self.assertIsNotNone(scope)
                self.assertEqual(scope["appliedFacets"], expected_facets)
                self.assertEqual(scope["searchText"], "")

    def test_retries_cloudflare_status_once(self) -> None:
        """Retry one time for throttling and Cloudflare edge failures."""

        for status_code in (429, 520, 521, 522, 523, 524):
            with self.subTest(status_code=status_code):
                failed_response = MagicMock()
                failed_response.status_code = status_code
                failed_response.headers = {}
                failed_response.raise_for_status.side_effect = (
                    api_client.requests.exceptions.HTTPError(
                        response=failed_response,
                    )
                )
                successful_response = MagicMock()
                successful_response.status_code = 200
                successful_response.json.return_value = {"jobs": []}

                with (
                    patch(
                        "scrapers.api.client.requests.get",
                        side_effect=[
                            failed_response,
                            successful_response,
                        ],
                    ) as get,
                    patch("scrapers.api.client.time.sleep") as sleep,
                    patch("builtins.print"),
                ):
                    jobs = scraper.fetch_ats_jobs(
                        self._company("greenhouse"),
                        scraper.ATS_FIELD_MAP["greenhouse"],
                    )

                self.assertEqual(jobs, [])
                self.assertEqual(get.call_count, 2)
                sleep.assert_called_once_with(
                    api_client.RETRY_DELAY_SECONDS
                )

    def test_retries_connection_and_timeout_errors_once(self) -> None:
        """Retry common transient transport failures one time."""

        errors = (
            api_client.requests.exceptions.ConnectionError(
                "connection reset"
            ),
            api_client.requests.exceptions.Timeout("request timed out"),
        )
        for error in errors:
            with self.subTest(error_type=type(error).__name__):
                response = MagicMock()
                response.json.return_value = {"jobs": []}
                with (
                    patch(
                        "scrapers.api.client.requests.get",
                        side_effect=[error, response],
                    ) as get,
                    patch("scrapers.api.client.time.sleep") as sleep,
                    patch("builtins.print"),
                ):
                    jobs = scraper.fetch_ats_jobs(
                        self._company("greenhouse"),
                        scraper.ATS_FIELD_MAP["greenhouse"],
                    )

                self.assertEqual(jobs, [])
                self.assertEqual(get.call_count, 2)
                sleep.assert_called_once_with(
                    api_client.RETRY_DELAY_SECONDS
                )

    def test_retry_respects_retry_after_header(self) -> None:
        """Use the server-provided retry delay when it is numeric."""

        failed_response = MagicMock()
        failed_response.status_code = 429
        failed_response.headers = {"Retry-After": "2"}
        failed_response.raise_for_status.side_effect = (
            api_client.requests.exceptions.HTTPError(
                response=failed_response,
            )
        )
        successful_response = MagicMock()
        successful_response.json.return_value = {"jobs": []}

        with (
            patch(
                "scrapers.api.client.requests.get",
                side_effect=[failed_response, successful_response],
            ),
            patch("scrapers.api.client.time.sleep") as sleep,
            patch("builtins.print"),
        ):
            jobs = scraper.fetch_ats_jobs(
                self._company("greenhouse"),
                scraper.ATS_FIELD_MAP["greenhouse"],
            )

        self.assertEqual(jobs, [])
        sleep.assert_called_once_with(2.0)

    def test_retry_after_header_is_capped(self) -> None:
        """Prevent excessive server retry delays from blocking the producer."""

        failed_response = MagicMock()
        failed_response.status_code = 429
        failed_response.headers = {"Retry-After": "3600"}
        failed_response.raise_for_status.side_effect = (
            api_client.requests.exceptions.HTTPError(
                response=failed_response,
            )
        )
        successful_response = MagicMock()
        successful_response.json.return_value = {"jobs": []}

        with (
            patch(
                "scrapers.api.client.requests.get",
                side_effect=[failed_response, successful_response],
            ),
            patch("scrapers.api.client.time.sleep") as sleep,
            patch("builtins.print"),
        ):
            jobs = scraper.fetch_ats_jobs(
                self._company("greenhouse"),
                scraper.ATS_FIELD_MAP["greenhouse"],
            )

        self.assertEqual(jobs, [])
        sleep.assert_called_once_with(5.0)

    def test_workday_mapping_handles_configured_http_status(self) -> None:
        """Return no jobs for Workday's configured auth error statuses."""

        response = MagicMock()
        response.status_code = 403
        error = api_client.requests.exceptions.HTTPError(response=response)
        response.raise_for_status.side_effect = error

        with (
            patch(
                "scrapers.api.client.requests.post",
                return_value=response,
            ),
            patch("scrapers.api.client.LOGGER.warning") as warning,
        ):
            jobs = scraper.fetch_ats_jobs(
                self._company("workday"),
                scraper.ATS_FIELD_MAP["workday"],
            )

        self.assertEqual(jobs, [])
        self.assertIn("403", str(warning.call_args))

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
            {
                "company_id": "iai",
                "ats_type": "custom",
                "fetch_strategy": "api",
                "is_active": True,
            },
        ]

        self.assertEqual(scraper.validate_company_routing(companies), [])

    def test_shared_custom_api_adapter_by_ats_type_is_routable(self) -> None:
        """Recognize ATS types served by one shared custom API adapter.

        ``fetch_jobs_from_company`` routes these through
        ``CUSTOM_API_ADAPTERS_BY_ATS_TYPE``; validation that does not know
        that registry reports healthy companies as unroutable every run.
        """

        companies = [
            {
                "company_id": "oracle",
                "ats_type": "oracle_recruiting_cloud",
                "fetch_strategy": "api",
                "is_active": True,
            },
            {
                "company_id": "akamai",
                "ats_type": "oracle_recruiting_cloud",
                "fetch_strategy": "api",
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


class CompanyConfigurationTests(unittest.TestCase):
    """Pin the production routes for previously silent zero-job sources."""

    @classmethod
    def setUpClass(cls) -> None:
        """Load production company configuration once for contract checks."""

        companies = scraper.load_json(
            scraper.CONFIG_DIR / "companies.json"
        )
        cls.companies = {
            company["company_id"]: company for company in companies
        }

    def test_iai_uses_hidden_json_api(self) -> None:
        """Route IAI through its current first-party JSON feed."""

        company = self.companies["iai"]
        self.assertEqual(company["ats_type"], "custom")
        self.assertEqual(company["fetch_strategy"], "api")
        self.assertEqual(
            company["api_url"],
            (
                "https://jobs.iai.co.il/wp-content/themes/tyco-wp/"
                "assets/json/jobs.json"
            ),
        )

    def test_amdocs_uses_pcsx_search_api(self) -> None:
        """Route Amdocs through its custom API adapter, not DOM scraping.

        The careers page is another Eightfold-family SPA whose job list
        never reaches the DOM (confirmed live), so this is fetched
        directly instead.
        """

        company = self.companies["amdocs"]
        self.assertEqual(company["ats_type"], "custom")
        self.assertEqual(company["fetch_strategy"], "api")
        self.assertEqual(
            company["api_url"],
            "https://jobs.amdocs.com/api/pcsx/search",
        )
        self.assertNotIn("job_selector", company)

    def test_oracle_and_akamai_use_oracle_rc_api(self) -> None:
        """Route both ORC tenants through the shared generic REST adapter.

        Akamai's own careers frontend is WAF-blocked (confirmed live,
        hard 403), but its Oracle Recruiting Cloud backend lives on a
        completely different oraclecloud.com host and is unaffected.
        """

        for company_id, site_number in (
            ("oracle", "CX_45001"),
            ("akamai", "CX_1"),
        ):
            with self.subTest(company_id=company_id):
                company = self.companies[company_id]
                self.assertEqual(
                    company["ats_type"], "oracle_recruiting_cloud"
                )
                self.assertEqual(company["fetch_strategy"], "api")
                self.assertIn("oraclecloud.com", company["api_url"])
                self.assertEqual(
                    company["oracle_site_number"], site_number
                )
                self.assertTrue(company["oracle_careers_url"])

    def test_elbit_uses_first_party_json_feed(self) -> None:
        """Route Elbit through its custom API adapter, not DOM scraping.

        The recruitment page is a Next.js shell whose job list never reaches
        the DOM as anchors (confirmed live), so this is fetched directly.
        """

        company = self.companies["elbit_systems"]
        self.assertEqual(company["ats_type"], "custom")
        self.assertEqual(company["fetch_strategy"], "api")
        self.assertEqual(
            company["api_url"],
            "https://elbitsystemscareer.com/cron/jobs.json",
        )
        self.assertNotIn("job_selector", company)

    def test_synopsys_uses_async_result_anchor(self) -> None:
        """Wait for actual job anchors without relying on a stale class."""

        company = self.companies["synopsys"]
        self.assertEqual(
            company["job_selector"],
            "#search-results-list a[data-job-id]",
        )

    def test_embedded_greenhouse_companies_use_public_api(self) -> None:
        """Bypass marketing-page iframes through official board APIs."""

        board_tokens = {
            "cato_networks": "catonetworks",
            "orca_security": "orcasecurity",
            "wiz": "wizinc",
        }
        for company_id, board_token in board_tokens.items():
            with self.subTest(company_id=company_id):
                company = self.companies[company_id]
                self.assertEqual(company["ats_type"], "greenhouse")
                self.assertEqual(company["fetch_strategy"], "api")
                self.assertEqual(
                    company["api_url"],
                    (
                        "https://boards-api.greenhouse.io/v1/boards/"
                        f"{board_token}/jobs?content=true"
                    ),
                )

    def test_cyera_uses_title_bearing_job_cards(self) -> None:
        """Select Cyera cards containing both the title field and job link."""

        company = self.companies["cyera"]
        self.assertEqual(
            company["job_selector"],
            (
                "div.positions_item:has([fs-list-field='itemTitle'])"
                ":has(a[href*='comeet.com/jobs/cyera/'])"
            ),
        )

    def test_phenom_companies_use_strict_job_listing_selectors(self) -> None:
        """Route browser Phenom sites to real job cards only."""

        expected_configs = {
            "palo_alto_networks": {
                "api_url": (
                    "https://jobs.paloaltonetworks.com/en/early-in-career"
                ),
                "job_selector": "a[data-job-id][href*='/job/']",
            },
            "servicenow": {
                "api_url": (
                    "https://careers.servicenow.com/jobs/"
                    "?search=&jobPostingType=Early+Career"
                    "&pagesize=20#results"
                ),
                "job_selector": (
                    "div.card.card-job:has("
                    "h2.card-title > a.stretched-link.js-view-job)"
                ),
            },
            "intuit": {
                "api_url": (
                    "https://jobs.intuit.com/search-jobs"
                    "?acm=9205024%2C9205760%2C9205744"
                    "&alrpm=ALL"
                    "&ascf=%5B%7B%22key%22%3A%22ALL%22%2C"
                    "%22value%22%3A%22%22%7D%5D"
                ),
                "job_selector": "a[data-job-id][href*='/job/']",
            },
        }
        for company_id, expected in expected_configs.items():
            with self.subTest(company_id=company_id):
                company = self.companies[company_id]
                self.assertEqual(company["ats_type"], "phenom")
                self.assertEqual(company["fetch_strategy"], "browser")
                self.assertEqual(company["api_url"], expected["api_url"])
                self.assertEqual(
                    company["job_selector"],
                    expected["job_selector"],
                )
                self.assertEqual(company["selector_timeout_ms"], 25_000)

    def test_imperva_uses_scoped_thales_widgets_api(self) -> None:
        """Route Imperva through the backend that honors country facets."""

        company = self.companies["imperva_thales"]
        self.assertEqual(company["ats_type"], "custom")
        self.assertEqual(company["fetch_strategy"], "api")
        self.assertEqual(
            company["api_url"],
            "https://careers.thalesgroup.com/widgets",
        )
        self.assertNotIn("job_selector", company)

    def test_meta_uses_network_interception_search_page(self) -> None:
        """Keep Meta on the page that emits its private GraphQL search."""

        company = self.companies["meta"]
        self.assertEqual(company["ats_type"], "meta_custom")
        self.assertEqual(company["fetch_strategy"], "browser")
        self.assertEqual(
            company["api_url"],
            "https://www.metacareers.com/jobs?q=Israel",
        )

    def test_google_uses_embedded_data_base_url(self) -> None:
        """Keep pagination queries out of Google's configured base URL."""

        company = self.companies["google"]
        self.assertEqual(company["ats_type"], "google_custom")
        self.assertEqual(company["fetch_strategy"], "browser")
        self.assertEqual(
            company["api_url"],
            (
                "https://www.google.com/about/careers/"
                "applications/jobs/results"
            ),
        )


class ScraperAdapterTests(unittest.TestCase):
    """Verify adapter transport bounds and factual content extraction."""

    def test_meta_parser_normalizes_graphql_jobs(self) -> None:
        """Normalize Meta's nested GraphQL result into shared job records."""

        payload = {
            "data": {
                "job_search_with_featured_jobs_v2": {
                    "all_jobs": [
                        {
                            "id": "123456789",
                            "title": "Software Engineer, University Grad",
                            "locations": ["Tel Aviv, Israel"],
                            "teams": ["Infrastructure", "AI Research"],
                        }
                    ]
                }
            }
        }

        jobs = custom_adapters._meta_job_search_parser(payload)

        self.assertEqual(
            jobs,
            [
                {
                    "id": "meta_123456789",
                    "title": "Software Engineer, University Grad",
                    "location": "Tel Aviv, Israel",
                    "url": (
                        "https://www.metacareers.com/jobs/123456789"
                    ),
                    "content": "Infrastructure, AI Research",
                }
            ],
        )

    def test_meta_parser_joins_locations_for_downstream_filter(self) -> None:
        """Keep secondary Meta locations visible to location filtering."""

        payload = {
            "data": {
                "job_search_with_featured_jobs_v2": {
                    "all_jobs": [
                        {
                            "id": "multi-location",
                            "title": "Software Engineer, University Grad",
                            "locations": [
                                "London, UK",
                                "Tel Aviv, Israel",
                            ],
                            "teams": [],
                        }
                    ]
                }
            }
        }

        jobs = custom_adapters._meta_job_search_parser(payload)

        self.assertEqual(
            jobs[0]["location"],
            "London, UK, Tel Aviv, Israel",
        )
        self.assertTrue(
            scraper.is_in_location(jobs[0]["location"], ["Israel"])
        )

    def test_meta_parser_ignores_malformed_jobs(self) -> None:
        """Return only complete Meta records from a partially bad payload."""

        payload = {
            "data": {
                "job_search_with_featured_jobs_v2": {
                    "all_jobs": [
                        {"id": "missing-title", "locations": []},
                        "not-an-object",
                    ]
                }
            }
        }

        self.assertEqual(
            custom_adapters._meta_job_search_parser(payload),
            [],
        )
        self.assertEqual(
            custom_adapters._meta_job_search_parser({"data": {}}),
            [],
        )

    def test_meta_adapter_uses_passive_graphql_interception(self) -> None:
        """Load Meta's search page and parse observed POST responses."""

        company = {
            "company_id": "meta",
            "company_name": "Meta Israel",
            "ats_type": "meta_custom",
            "fetch_strategy": "browser",
            "api_url": "https://www.metacareers.com/jobs?q=Israel",
        }
        expected_jobs = [{
            "id": "meta_123",
            "title": "University Grad Engineer",
            "location": "Tel Aviv, Israel",
            "url": "https://www.metacareers.com/jobs/123",
            "content": "Infrastructure",
        }]
        with patch(
            "scrapers.browser.custom_adapters.NetworkInterceptScraper"
        ) as scraper_class:
            scraper_class.return_value.scrape.return_value = ScrapeResult(
                status=ScrapeStatus.SUCCESS,
                jobs=expected_jobs,
            )

            jobs = custom_adapters.scrape_meta(company)

        self.assertEqual(jobs, expected_jobs)
        scraper_class.return_value.scrape.assert_called_once_with(
            company=company,
            target_url_pattern="/graphql",
            response_parser_fn=custom_adapters._meta_job_search_parser,
            request_method="POST",
        )

    def test_meta_custom_routes_to_registered_adapter(self) -> None:
        """Dispatch Meta through interception instead of DOM heuristics."""

        company = {
            **self._company("meta_custom"),
            "fetch_strategy": "browser",
        }
        expected_jobs = [{"id": "meta_123"}]
        adapter = MagicMock(return_value=expected_jobs)
        with (
            patch.dict(
                scraper.CUSTOM_BROWSER_ADAPTERS,
                {"meta_custom": adapter},
            ),
            patch("builtins.print"),
        ):
            jobs = scraper.fetch_jobs_from_company(company)

        self.assertEqual(jobs, expected_jobs)
        adapter.assert_called_once_with(company)

    def test_google_text_reads_second_list_item_only(self) -> None:
        """Read Google's HTML-bearing pair without guessing other shapes."""

        self.assertEqual(
            custom_adapters._google_text([None, "<p>Job details</p>"]),
            "<p>Job details</p>",
        )
        self.assertEqual(custom_adapters._google_text(["only-one"]), "")
        self.assertEqual(custom_adapters._google_text("plain text"), "")

    def test_google_parser_maps_fields_and_skips_malformed_jobs(self) -> None:
        """Normalize positional Google data while isolating bad records."""

        valid_job: list[object] = [None] * 20
        valid_job[0] = 12345
        valid_job[1] = "Software Engineering Intern"
        valid_job[2] = "https://www.google.com/about/careers/jobs/12345"
        valid_job[3] = [None, "<p>Job description</p>"]
        valid_job[4] = [None, "<p>Minimum qualifications</p>"]
        valid_job[9] = [
            ["Tel Aviv, Israel", "IL"],
            ["Haifa, Israel", "IL"],
        ]
        valid_job[10] = [None, "<p>Responsibilities</p>"]
        valid_job[19] = [None, "must not be included"]

        with patch(
            "scrapers.browser.custom_adapters.LOGGER.warning"
        ) as warning:
            jobs = custom_adapters._google_job_parser(
                [["malformed", valid_job]]
            )

        self.assertEqual(
            jobs,
            [{
                "id": "google_12345",
                "title": "Software Engineering Intern",
                "location": "Tel Aviv, Israel, Haifa, Israel",
                "url": (
                    "https://www.google.com/about/careers/jobs/12345"
                ),
                "content": (
                    "<p>Job description</p>\n\n"
                    "<p>Minimum qualifications</p>\n\n"
                    "<p>Responsibilities</p>"
                ),
            }],
        )
        self.assertNotIn("must not be included", jobs[0]["content"])
        warning.assert_called_once()

    def test_google_parser_handles_missing_location_list(self) -> None:
        """Use an empty location when Google's positional field is absent."""

        job: list[object] = [None] * 11
        job[0] = "no-location"
        job[1] = "Early Career Software Engineer"
        job[2] = "https://example.test/jobs/no-location"
        job[3] = [None, "Description"]
        job[4] = [None, "Qualifications"]
        job[9] = None
        job[10] = [None, "Responsibilities"]

        jobs = custom_adapters._google_job_parser([[job]])

        self.assertEqual(jobs[0]["location"], "")

    def test_google_adapter_paginates_variants_and_deduplicates(self) -> None:
        """Fetch both Google variants until empty and preserve first IDs."""

        company = {
            "company_id": "google",
            "company_name": "Google Israel",
            "ats_type": "google_custom",
            "fetch_strategy": "browser",
            "api_url": (
                "https://www.google.com/about/careers/"
                "applications/jobs/results"
            ),
        }
        early_job = {
            "id": "google_early",
            "title": "Early Career Engineer",
            "location": "Israel",
            "url": "https://example.test/jobs/early",
            "content": "Early career",
        }
        shared_early_job = {
            "id": "google_shared",
            "title": "Shared Role - Early Variant",
            "location": "Israel",
            "url": "https://example.test/jobs/shared",
            "content": "First occurrence",
        }
        shared_intern_job = {
            **shared_early_job,
            "title": "Shared Role - Intern Variant",
            "content": "Duplicate occurrence",
        }
        intern_job = {
            "id": "google_intern",
            "title": "Software Engineering Intern",
            "location": "Tel Aviv, Israel",
            "url": "https://example.test/jobs/intern",
            "content": "Internship",
        }

        with patch(
            "scrapers.browser.custom_adapters.EmbeddedJsonScraper"
        ) as scraper_class:
            scraper_class.return_value.scrape.side_effect = [
                ScrapeResult(
                    status=ScrapeStatus.SUCCESS,
                    jobs=[early_job, shared_early_job],
                ),
                ScrapeResult(status=ScrapeStatus.NO_JOBS, jobs=[]),
                ScrapeResult(
                    status=ScrapeStatus.SUCCESS,
                    jobs=[shared_intern_job, intern_job],
                ),
                ScrapeResult(status=ScrapeStatus.SUCCESS, jobs=[]),
            ]

            jobs = custom_adapters.scrape_google(company)

        self.assertEqual(
            jobs,
            [early_job, shared_early_job, intern_job],
        )
        scraper_class.assert_called_once_with()
        base_url = company["api_url"]
        self.assertEqual(
            scraper_class.return_value.scrape.call_args_list,
            [
                call(
                    company={
                        **company,
                        "api_url": (
                            f"{base_url}?location=Israel"
                            "&target_level=EARLY&page=1"
                        ),
                    },
                    data_parser_fn=custom_adapters._google_job_parser,
                    write_diagnostics=True,
                ),
                call(
                    company={
                        **company,
                        "api_url": (
                            f"{base_url}?location=Israel"
                            "&target_level=EARLY&page=2"
                        ),
                    },
                    data_parser_fn=custom_adapters._google_job_parser,
                    write_diagnostics=False,
                ),
                call(
                    company={
                        **company,
                        "api_url": (
                            f"{base_url}?location=Israel"
                            "&employment_type=INTERN&page=1"
                        ),
                    },
                    data_parser_fn=custom_adapters._google_job_parser,
                    write_diagnostics=False,
                ),
                call(
                    company={
                        **company,
                        "api_url": (
                            f"{base_url}?location=Israel"
                            "&employment_type=INTERN&page=2"
                        ),
                    },
                    data_parser_fn=custom_adapters._google_job_parser,
                    write_diagnostics=False,
                ),
            ],
        )

    def test_google_adapter_caps_each_query_variant(self) -> None:
        """Stop each Google query independently at the safety limit."""

        company = {
            "company_id": "google",
            "api_url": (
                "https://www.google.com/about/careers/"
                "applications/jobs/results"
            ),
        }
        repeated_job = {
            "id": "google_repeated",
            "title": "Early Career Engineer",
            "location": "Israel",
            "url": "https://example.test/jobs/repeated",
            "content": "Repeated across pages",
        }

        with (
            patch(
                "scrapers.browser.custom_adapters.EmbeddedJsonScraper"
            ) as scraper_class,
            patch.object(
                custom_adapters,
                "GOOGLE_MAX_PAGES_PER_VARIANT",
                2,
            ),
            patch(
                "scrapers.browser.custom_adapters.LOGGER.warning"
            ) as warning,
        ):
            scraper_class.return_value.scrape.return_value = ScrapeResult(
                status=ScrapeStatus.SUCCESS,
                jobs=[repeated_job],
            )

            jobs = custom_adapters.scrape_google(company)

        self.assertEqual(jobs, [repeated_job])
        self.assertEqual(
            scraper_class.return_value.scrape.call_count,
            4,
        )
        self.assertEqual(warning.call_count, 2)
        called_urls = [
            item.kwargs["company"]["api_url"]
            for item in scraper_class.return_value.scrape.call_args_list
        ]
        self.assertFalse(any("page=3" in url for url in called_urls))

    def test_google_custom_routes_to_registered_adapter(self) -> None:
        """Dispatch Google through embedded extraction instead of DOM rules."""

        company = {
            **self._company("google_custom"),
            "fetch_strategy": "browser",
        }
        expected_jobs = [{"id": "google_123"}]
        adapter = MagicMock(return_value=expected_jobs)
        with (
            patch.dict(
                scraper.CUSTOM_BROWSER_ADAPTERS,
                {"google_custom": adapter},
            ),
            patch("builtins.print"),
        ):
            jobs = scraper.fetch_jobs_from_company(company)

        self.assertEqual(jobs, expected_jobs)
        adapter.assert_called_once_with(company)

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
            patch(
                "scrapers.api.client.requests.get",
                return_value=response,
            ) as get,
            patch("builtins.print"),
        ):
            jobs = scraper.fetch_jobs_from_company(
                self._company("greenhouse")
            )

        get.assert_called_once_with(
            "https://example.test/api",
            headers=api_client.DEFAULT_REQUEST_HEADERS,
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
                "scrapers.api.client.requests.post",
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
                        "scrapers.api.client.requests.get",
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

    def test_iai_normalizes_hidden_json_feed(self) -> None:
        """Extract IAI's compact array fields into the shared job schema."""

        response = MagicMock()
        response.json.return_value = [
            {
                "id": 76049533,
                "tl": "Student Software Engineer",
                "ct": "Beer Yaakov",
                "dc": "Develop real-time C++ systems.",
            },
            "ignore non-object entries",
            {"id": 123, "ct": "Lod"},
        ]
        company = {
            "company_id": "iai",
            "company_name": "Israel Aerospace Industries (IAI)",
            "ats_type": "custom",
            "fetch_strategy": "api",
            "api_url": (
                "https://jobs.iai.co.il/wp-content/themes/tyco-wp/"
                "assets/json/jobs.json"
            ),
        }

        with patch(
            "scrapers.browser.custom_adapters.requests.get",
            return_value=response,
        ) as get:
            jobs = custom_adapters.scrape_iai(company)

        response.raise_for_status.assert_called_once_with()
        self.assertEqual(get.call_args.args[0], company["api_url"])
        self.assertEqual(get.call_args.kwargs["timeout"], 15)
        self.assertIn("User-Agent", get.call_args.kwargs["headers"])
        self.assertEqual(
            jobs,
            [
                {
                    "id": "iai_76049533",
                    "title": "Student Software Engineer",
                    "location": "Beer Yaakov",
                    "url": "https://jobs.iai.co.il/job/76049533/",
                    "content": "Develop real-time C++ systems.",
                }
            ],
        )

    def test_iai_custom_api_routes_to_registered_adapter(self) -> None:
        """Dispatch IAI's custom API instead of silently returning no jobs."""

        company = {
            "company_id": "iai",
            "company_name": "Israel Aerospace Industries (IAI)",
            "ats_type": "custom",
            "fetch_strategy": "api",
            "api_url": "https://jobs.iai.co.il/jobs.json",
        }
        expected_jobs = [{"id": "iai_76049533"}]
        adapter = MagicMock(return_value=expected_jobs)

        with (
            patch.dict(
                scraper.CUSTOM_API_ADAPTERS,
                {"iai": adapter},
            ),
            patch("builtins.print"),
        ):
            jobs = scraper.fetch_jobs_from_company(company)

        self.assertEqual(jobs, expected_jobs)
        adapter.assert_called_once_with(company)

    def test_elbit_normalizes_first_party_json_feed(self) -> None:
        """Extract Elbit's cron/jobs.json feed into the shared job schema."""

        response = MagicMock()
        response.json.return_value = [
            {
                "jobId": 20839,
                "jobTitle": "Electronics Development Engineer",
                "area": "Shfela",
                "description": (
                    "&lt;div&gt;Design multidisciplinary systems.&lt;/div&gt;"
                    "&lt;div&gt;&lt;br&gt;&lt;/div&gt;"
                ),
            },
            "ignore non-object entries",
            {"jobId": 1, "area": "North"},  # missing title, skipped
            {"jobTitle": "No id", "area": "Center"},  # missing id, skipped
            {"jobId": 2, "jobTitle": "No area listed", "area": None},
        ]
        company = {
            "company_id": "elbit_systems",
            "company_name": "Elbit Systems",
            "ats_type": "custom",
            "fetch_strategy": "api",
            "api_url": "https://elbitsystemscareer.com/cron/jobs.json",
        }

        with patch(
            "scrapers.browser.custom_adapters.requests.get",
            return_value=response,
        ) as get:
            jobs = custom_adapters.scrape_elbit(company)

        response.raise_for_status.assert_called_once_with()
        self.assertEqual(get.call_args.args[0], company["api_url"])
        self.assertEqual(get.call_args.kwargs["timeout"], 15)
        self.assertIn("User-Agent", get.call_args.kwargs["headers"])
        self.assertEqual(
            jobs,
            [
                {
                    "id": "elbit_systems_20839",
                    "title": "Electronics Development Engineer",
                    "location": "Shfela",
                    "url": (
                        "https://elbitsystemscareer.com/Recruitment-Page/"
                        "?jobId=20839"
                    ),
                    "content": "Design multidisciplinary systems.",
                },
                {
                    "id": "elbit_systems_2",
                    "title": "No area listed",
                    "location": "",
                    "url": (
                        "https://elbitsystemscareer.com/Recruitment-Page/"
                        "?jobId=2"
                    ),
                    "content": "",
                },
            ],
        )

    def test_elbit_requires_api_url(self) -> None:
        """Fail closed instead of guessing an endpoint."""

        with patch(
            "scrapers.browser.custom_adapters.requests.get",
        ) as get:
            jobs = custom_adapters.scrape_elbit({"company_id": "elbit_systems"})

        get.assert_not_called()
        self.assertEqual(jobs, [])

    def test_elbit_rejects_non_list_payload(self) -> None:
        """Tolerate an unexpected feed shape without raising."""

        response = MagicMock()
        response.json.return_value = {"unexpected": "shape"}
        company = {
            "company_id": "elbit_systems",
            "api_url": "https://elbitsystemscareer.com/cron/jobs.json",
        }

        with patch(
            "scrapers.browser.custom_adapters.requests.get",
            return_value=response,
        ):
            jobs = custom_adapters.scrape_elbit(company)

        self.assertEqual(jobs, [])

    def test_elbit_custom_api_routes_to_registered_adapter(self) -> None:
        """Dispatch Elbit's custom API instead of the browser fallback."""

        company = {
            "company_id": "elbit_systems",
            "company_name": "Elbit Systems",
            "ats_type": "custom",
            "fetch_strategy": "api",
            "api_url": "https://elbitsystemscareer.com/cron/jobs.json",
        }
        expected_jobs = [{"id": "elbit_systems_20839"}]
        adapter = MagicMock(return_value=expected_jobs)

        with (
            patch.dict(
                scraper.CUSTOM_API_ADAPTERS,
                {"elbit_systems": adapter},
            ),
            patch("builtins.print"),
        ):
            jobs = scraper.fetch_jobs_from_company(company)

        self.assertEqual(jobs, expected_jobs)
        adapter.assert_called_once_with(company)

    def test_amdocs_paginates_via_start_offset_and_builds_urls(self) -> None:
        """Page through pcsx/search unconditionally, no location filter.

        The frontend's own location=israel param returns zero results even
        from a real authenticated browser session (verified live), so this
        fetches the domain unconditionally and relies on the orchestrator's
        location_filters to scope results downstream.
        """

        first_response = MagicMock()
        first_response.json.return_value = {
            "data": {
                "positions": [
                    {
                        "id": 563431014700743,
                        "name": "Category Manager, Strategic Sourcing",
                        "standardizedLocations": ["Miami, FL, US"],
                        "positionUrl": "/careers/job/563431014700743",
                    },
                    {
                        "id": 563431014721199,
                        "name": "Student Developer",
                        "standardizedLocations": ["Ra'anana, Israel"],
                        "positionUrl": "/careers/job/563431014721199",
                    },
                ]
                * 5  # 10 positions: a full first page
            }
        }
        second_response = MagicMock()
        second_response.json.return_value = {"data": {"positions": []}}
        company = {
            "company_id": "amdocs",
            "ats_type": "custom",
            "fetch_strategy": "api",
            "api_url": "https://jobs.amdocs.com/api/pcsx/search",
        }

        with patch(
            "scrapers.browser.custom_adapters.requests.get",
            side_effect=[first_response, second_response],
        ) as get:
            jobs = custom_adapters.scrape_amdocs(company)

        self.assertEqual(get.call_count, 2)
        self.assertEqual(get.call_args_list[0].kwargs["params"]["start"], 0)
        self.assertEqual(get.call_args_list[1].kwargs["params"]["start"], 10)
        self.assertEqual(len(jobs), 2)  # deduped by id, 5x repeats collapse
        self.assertEqual(
            jobs[0],
            {
                "id": "amdocs_563431014700743",
                "title": "Category Manager, Strategic Sourcing",
                "location": "Miami, FL, US",
                "url": "https://jobs.amdocs.com/careers/job/563431014700743",
                "content": "",
            },
        )
        self.assertEqual(jobs[1]["location"], "Ra'anana, Israel")

    def test_amdocs_requires_api_url(self) -> None:
        """Fail closed instead of guessing an endpoint."""

        with patch(
            "scrapers.browser.custom_adapters.requests.get",
        ) as get:
            jobs = custom_adapters.scrape_amdocs({"company_id": "amdocs"})

        get.assert_not_called()
        self.assertEqual(jobs, [])

    def test_amdocs_custom_api_routes_to_registered_adapter(self) -> None:
        """Dispatch Amdocs' custom API instead of the browser fallback."""

        company = {
            "company_id": "amdocs",
            "ats_type": "custom",
            "fetch_strategy": "api",
            "api_url": "https://jobs.amdocs.com/api/pcsx/search",
        }
        expected_jobs = [{"id": "amdocs_1"}]
        adapter = MagicMock(return_value=expected_jobs)

        with (
            patch.dict(
                scraper.CUSTOM_API_ADAPTERS,
                {"amdocs": adapter},
            ),
            patch("builtins.print"),
        ):
            jobs = scraper.fetch_jobs_from_company(company)

        self.assertEqual(jobs, expected_jobs)
        adapter.assert_called_once_with(company)

    def test_oracle_rc_paginates_by_offset_and_joins_locations(self) -> None:
        """Page a generic ORC tenant via offset and stop at TotalJobsCount.

        A full first page (matching ORC_PAGE_SIZE exactly) must trigger a
        second request; the mock data reflects that instead of an
        unrealistically short first page.
        """

        first_page_requisitions = [
            {
                "Id": f"{300000 + index}",
                "Title": f"Engineer {index}",
                "PrimaryLocation": "PETACH TIKVA, Israel",
                "secondaryLocations": [],
                "ShortDescriptionStr": "",
            }
            for index in range(custom_adapters.ORC_PAGE_SIZE)
        ]
        first_page_requisitions[0] = {
            "Id": "342302",
            "Title": "Program Management VP",
            "PrimaryLocation": "PETACH TIKVA, Israel",
            "secondaryLocations": [
                {"Name": "Tel Aviv, Israel"},
                {"Name": "PETACH TIKVA, Israel"},
            ],
            "ShortDescriptionStr": "Lead cloud operations.",
        }
        total_jobs = custom_adapters.ORC_PAGE_SIZE + 1

        first_response = MagicMock()
        first_response.json.return_value = {
            "items": [{
                "TotalJobsCount": total_jobs,
                "requisitionList": first_page_requisitions,
            }]
        }
        second_response = MagicMock()
        second_response.json.return_value = {
            "items": [{
                "TotalJobsCount": total_jobs,
                "requisitionList": [
                    {
                        "Id": "340882",
                        "Title": "Senior Site Reliability Engineer",
                        "PrimaryLocation": "PETACH TIKVA, Israel",
                    },
                ],
            }]
        }
        company = {
            "company_id": "oracle",
            "ats_type": "oracle_recruiting_cloud",
            "fetch_strategy": "api",
            "api_url": (
                "https://eeho.fa.us2.oraclecloud.com/hcmRestApi/"
                "resources/latest/recruitingCEJobRequisitions"
            ),
            "oracle_site_number": "CX_45001",
            "oracle_careers_url": (
                "https://careers.oracle.com/en/sites/jobsearch/job/"
            ),
            "location_filters": ["Israel", "Petah Tikva"],
        }

        with patch(
            "scrapers.browser.custom_adapters.requests.get",
            side_effect=[first_response, second_response],
        ) as get:
            jobs = custom_adapters.scrape_oracle_rc(company)

        self.assertEqual(get.call_count, 2)
        self.assertIn(
            "keyword=Israel",
            get.call_args_list[0].kwargs["params"]["finder"],
        )
        self.assertIn(
            "siteNumber=CX_45001",
            get.call_args_list[0].kwargs["params"]["finder"],
        )
        self.assertIn(
            f"offset={custom_adapters.ORC_PAGE_SIZE}",
            get.call_args_list[1].kwargs["params"]["finder"],
        )
        self.assertEqual(
            len(jobs),
            custom_adapters.ORC_PAGE_SIZE + 1,
        )
        self.assertEqual(jobs[-1]["id"], "oracle_340882")
        self.assertEqual(
            jobs[0]["location"],
            "PETACH TIKVA, Israel, Tel Aviv, Israel",
        )
        self.assertEqual(
            jobs[0]["url"],
            "https://careers.oracle.com/en/sites/jobsearch/job/342302",
        )
        self.assertEqual(jobs[0]["content"], "Lead cloud operations.")
        self.assertEqual(jobs[1]["content"], "")

    def test_oracle_rc_requires_site_number(self) -> None:
        """Fail closed without a tenant site number to scope the finder."""

        with patch(
            "scrapers.browser.custom_adapters.requests.get",
        ) as get:
            jobs = custom_adapters.scrape_oracle_rc({
                "company_id": "akamai",
                "api_url": "https://fa-extu-saasfaprod1.fa.ocs.oraclecloud.com/x",
            })

        get.assert_not_called()
        self.assertEqual(jobs, [])

    def test_oracle_rc_defaults_keyword_to_israel_without_location_filters(
        self,
    ) -> None:
        """Default the finder keyword when a company has no filters set."""

        response = MagicMock()
        response.json.return_value = {"items": [{"requisitionList": []}]}
        company = {
            "company_id": "akamai",
            "api_url": "https://fa-extu-saasfaprod1.fa.ocs.oraclecloud.com/x",
            "oracle_site_number": "CX_1",
        }

        with patch(
            "scrapers.browser.custom_adapters.requests.get",
            return_value=response,
        ) as get:
            custom_adapters.scrape_oracle_rc(company)

        self.assertIn(
            "keyword=Israel",
            get.call_args.kwargs["params"]["finder"],
        )

    def test_oracle_recruiting_cloud_routes_to_registered_adapter(
        self,
    ) -> None:
        """Dispatch any ORC tenant through the shared generic adapter."""

        company = {
            "company_id": "akamai",
            "company_name": "Akamai Israel",
            "ats_type": "oracle_recruiting_cloud",
            "fetch_strategy": "api",
            "api_url": "https://fa-extu-saasfaprod1.fa.ocs.oraclecloud.com/x",
            "oracle_site_number": "CX_1",
        }
        expected_jobs = [{"id": "akamai_1"}]
        adapter = MagicMock(return_value=expected_jobs)

        with (
            patch.dict(
                scraper.CUSTOM_API_ADAPTERS_BY_ATS_TYPE,
                {"oracle_recruiting_cloud": adapter},
            ),
            patch("builtins.print"),
        ):
            jobs = scraper.fetch_jobs_from_company(company)

        self.assertEqual(jobs, expected_jobs)
        adapter.assert_called_once_with(company)

    def test_thales_adapter_scopes_israel_and_paginates(self) -> None:
        """Normalize every Israel page and reject foreign contamination."""

        first_response = MagicMock()
        first_response.json.return_value = {
            "refineSearch": {
                "totalHits": 3,
                "data": {
                    "jobs": [
                        {
                            "jobId": "R100",
                            "title": "Student C++ Engineer",
                            "country": "Israel",
                            "cityStateCountry": "Rehovot, Israel",
                            "location": "Rehovot, 7670212",
                            "address": (
                                "Perkeris Street 2, Rehovot, Israel"
                            ),
                            "applyUrl": (
                                "https://thales.example/jobs/R100/apply"
                            ),
                            "descriptionTeaser": (
                                "Develop networking software."
                            ),
                        },
                        {
                            "jobId": "R200",
                            "title": "Graduate Engineer",
                            "country": "France",
                            "cityStateCountry": "Paris, France",
                            "applyUrl": (
                                "https://thales.example/jobs/R200/apply"
                            ),
                        },
                    ]
                },
            }
        }
        second_response = MagicMock()
        second_response.json.return_value = {
            "refineSearch": {
                "totalHits": 3,
                "data": {
                    "jobs": [
                        {
                            "jobId": "R300",
                            "title": "Junior Software Engineer",
                            "country": "Israel",
                            "cityStateCountry": "Tel Aviv, Israel",
                            "location": "Tel Aviv, 67010",
                            "applyUrl": (
                                "https://thales.example/jobs/R300/apply"
                            ),
                            "descriptionTeaser": (
                                "Build application-security systems."
                            ),
                        }
                    ]
                },
            }
        }
        company = {
            "company_id": "imperva_thales",
            "ats_type": "custom",
            "fetch_strategy": "api",
            "api_url": "https://careers.thalesgroup.com/widgets",
        }

        with patch(
            "scrapers.browser.custom_adapters.requests.post",
            side_effect=[first_response, second_response],
        ) as post:
            jobs = custom_adapters.scrape_thales_phenom(company)

        self.assertEqual(
            [job["id"] for job in jobs],
            ["imperva_thales_R100", "imperva_thales_R300"],
        )
        self.assertEqual(jobs[0]["title"], "Student C++ Engineer")
        self.assertIn("Rehovot, Israel", jobs[0]["location"])
        self.assertEqual(
            jobs[0]["url"],
            "https://thales.example/jobs/R100/apply",
        )
        self.assertEqual(
            jobs[0]["content"],
            "Develop networking software.",
        )
        self.assertEqual(post.call_count, 2)
        first_payload = post.call_args_list[0].kwargs["json"]
        second_payload = post.call_args_list[1].kwargs["json"]
        self.assertEqual(
            first_payload["selected_fields"],
            {"country": ["Israel"]},
        )
        self.assertEqual(first_payload["from"], 0)
        self.assertEqual(second_payload["from"], 2)
        self.assertEqual(post.call_args.kwargs["timeout"], 15)
        self.assertIn("User-Agent", post.call_args.kwargs["headers"])

    def test_imperva_custom_api_routes_to_registered_adapter(self) -> None:
        """Dispatch Imperva through the scoped Thales API adapter."""

        self.assertIs(
            scraper.CUSTOM_API_ADAPTERS["imperva_thales"],
            custom_adapters.scrape_thales_phenom,
        )

    def test_successfactors_missing_location_stays_unknown(self) -> None:
        """Do not fabricate Israel when a SuccessFactors row has no location."""

        response = MagicMock()
        response.text = (
            '<table><tr class="data-row">'
            '<span class="jobTitle">'
            '<a href="/jobs/123/">Student Engineer</a>'
            "</span></tr></table>"
        )
        with patch(
            "scrapers.browser.custom_adapters.requests.get",
            return_value=response,
        ):
            jobs = custom_adapters.scrape_successfactors(
                self._company("successfactors")
            )

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["location"], "")

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
                "scrapers.orchestrator.scrape_eightfold",
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
                "scrapers.orchestrator.scrape_universal_playwright",
                return_value=expected_jobs,
            ) as universal_playwright,
            patch("builtins.print"),
        ):
            jobs = scraper.fetch_jobs_from_company(company)

        self.assertEqual(jobs, expected_jobs)
        universal_playwright.assert_called_once_with(company)

    def test_unknown_ats_emits_logging_warning(self) -> None:
        """Make unsupported ATS types visible through standard logging."""

        with patch("scrapers.orchestrator.LOGGER.warning") as warning:
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


class ComeetAdapterTests(unittest.TestCase):
    """Verify the generalized Comeet adapter across its three embed shapes."""

    def test_direct_board_parses_embedded_positions_data(self) -> None:
        """Extract jobs from a board's inline COMPANY_POSITIONS_DATA array."""

        html_response = MagicMock()
        html_response.text = """
        <html><script>
        window.COMPANY_POSITIONS_DATA = [{
            "name": "Student Software Engineer",
            "uid": "34.C6F",
            "location": {"city": "Ramat-Gan", "state": "Tel Aviv District", "name": "Israel"},
            "url_active_page": "https://wsc-sports.com/career/student-swe/",
            "url_comeet_hosted_page": "https://www.comeet.com/jobs/wsc-sports/93.007/x/34.C6F",
            "custom_fields": {"details": [{"name": "Description", "value": "<p>Build things.</p>"}]}
        }];
        </script></html>
        """
        company = {
            "company_id": "wsc_sports",
            "api_url": "https://www.comeet.com/jobs/wsc-sports/93.007",
        }

        with patch(
            "scrapers.browser.custom_adapters.requests.get",
            return_value=html_response,
        ) as get:
            jobs = custom_adapters.scrape_comeet(company)

        self.assertEqual(get.call_count, 1)
        self.assertEqual(get.call_args.args[0], company["api_url"])
        self.assertEqual(
            jobs,
            [
                {
                    "id": "wsc_sports_34.C6F",
                    "title": "Student Software Engineer",
                    "location": "Ramat-Gan | Tel Aviv District | Israel",
                    "url": "https://wsc-sports.com/career/student-swe/",
                    "content": "Build things.",
                }
            ],
        )

    def test_js_widget_embed_derives_and_fetches_direct_board(self) -> None:
        """Follow a COMEET.init widget's own company-name/uid to the board."""

        widget_response = MagicMock()
        widget_response.text = """
        <script>
        COMEET.init({"token": "X", "company-uid": "C0.008", "company-name": "Checkmarx"});
        </script>
        """
        board_response = MagicMock()
        board_response.text = """
        window.COMPANY_POSITIONS_DATA = [{
            "name": "AppSec Engineer", "uid": "78.66E",
            "location": {"city": "Tel Aviv", "name": "Israel"},
            "url_active_page": "https://checkmarx.com/jobs/78.66E",
            "custom_fields": {}
        }];
        """
        company = {"company_id": "checkmarx", "api_url": "https://checkmarx.com/company/careers/"}

        with patch(
            "scrapers.browser.custom_adapters.requests.get",
            side_effect=[widget_response, board_response],
        ) as get:
            jobs = custom_adapters.scrape_comeet(company)

        self.assertEqual(get.call_count, 2)
        self.assertEqual(
            get.call_args_list[1].args[0],
            "https://www.comeet.com/jobs/checkmarx/C0.008",
        )
        self.assertEqual(
            jobs,
            [
                {
                    "id": "checkmarx_78.66E",
                    "title": "AppSec Engineer",
                    "location": "Tel Aviv | Israel",
                    "url": "https://checkmarx.com/jobs/78.66E",
                    "content": "",
                }
            ],
        )

    def test_widget_falls_back_to_domain_slug_when_name_slug_has_no_data(
        self,
    ) -> None:
        """Try a domain-derived slug when the display-name slug is wrong.

        Confirmed live: Moon Active's widget declares "company-name":
        "Moon Active", but the real Comeet slug is "moonactive" -- the
        naive "moon-active" slug 302-redirects to Comeet's own homepage
        (a 200 with no position data), not an error.
        """

        widget_response = MagicMock()
        widget_response.text = """
        <script>
        COMEET.init({"token": "X", "company-uid": "A2.00C", "company-name": "Moon Active"});
        </script>
        """
        wrong_slug_response = MagicMock()
        wrong_slug_response.text = "<html>Comeet homepage, no position data here</html>"
        right_slug_response = MagicMock()
        right_slug_response.text = """
        window.COMPANY_POSITIONS_DATA = [{
            "name": "Game Designer", "uid": "11.111",
            "location": {"name": "Israel"}, "url_active_page": "https://moonactive.com/jobs/11",
            "custom_fields": {}
        }];
        """
        company = {"company_id": "moon_active", "api_url": "https://www.moonactive.com/careers/"}

        with patch(
            "scrapers.browser.custom_adapters.requests.get",
            side_effect=[widget_response, wrong_slug_response, right_slug_response],
        ) as get:
            jobs = custom_adapters.scrape_comeet(company)

        self.assertEqual(get.call_count, 3)
        self.assertEqual(
            get.call_args_list[1].args[0],
            "https://www.comeet.com/jobs/moon-active/A2.00C",
        )
        self.assertEqual(
            get.call_args_list[2].args[0],
            "https://www.comeet.com/jobs/moonactive/A2.00C",
        )
        self.assertEqual(jobs[0]["id"], "moon_active_11.111")

    def test_wordpress_plugin_dom_fallback_when_no_widget_or_data(self) -> None:
        """DOM-scrape server-rendered positions from Comeet's WP plugin.

        This embed shape (confirmed live on ChargeAfter) exposes neither
        COMPANY_POSITIONS_DATA nor a COMEET.init widget -- positions are
        rendered directly as .comeet-position elements with no separate
        structured location or description field.
        """

        html_response = MagicMock()
        html_response.text = """
        <html><body>
        <div class="comeet-position">
            <a href="/careers/co/remote/41.B6E/customer-success">
                <div class="comeet-position-name">Customer Success Manager</div>
                <div class="comeet-position-meta">Remote | Full-time</div>
            </a>
        </div>
        </body></html>
        """
        company = {"company_id": "chargeafter", "api_url": "https://chargeafter.com/careers/"}

        with patch(
            "scrapers.browser.custom_adapters.requests.get",
            return_value=html_response,
        ):
            jobs = custom_adapters.scrape_comeet(company)

        self.assertEqual(
            jobs,
            [
                {
                    "id": "chargeafter_41.B6E",
                    "title": "Customer Success Manager",
                    "location": "Remote | Full-time",
                    "url": "https://chargeafter.com/careers/co/remote/41.B6E/customer-success",
                    "content": "",
                }
            ],
        )

    def test_wordpress_plugin_dom_fallback_when_position_is_the_anchor(
        self,
    ) -> None:
        """Handle the WP-plugin shape where .comeet-position is itself <a>.

        Confirmed live on Nuvoton: unlike ChargeAfter's wrapper-div-around-
        an-anchor markup, some renders of this plugin put the href directly
        on the ".comeet-position" element. A version of this adapter that
        only looked for a *nested* anchor silently returned zero jobs here
        despite genuine, correctly-rendered position data being present.
        """

        html_response = MagicMock()
        html_response.text = """
        <html><body>
        <a class="comeet-position" href="https://nuvoton.co.il/careers/co/ai-npu/3B.969/lead">
            <div class="comeet-position-name">Lead AI Engineer</div>
            <div class="comeet-position-meta">Nuvoton-Herzliya | Full-time</div>
        </a>
        </body></html>
        """
        company = {"company_id": "nuvoton", "api_url": "https://nuvoton.co.il/careers/"}

        with patch(
            "scrapers.browser.custom_adapters.requests.get",
            return_value=html_response,
        ):
            jobs = custom_adapters.scrape_comeet(company)

        self.assertEqual(
            jobs,
            [
                {
                    "id": "nuvoton_3B.969",
                    "title": "Lead AI Engineer",
                    "location": "Nuvoton-Herzliya | Full-time",
                    "url": "https://nuvoton.co.il/careers/co/ai-npu/3B.969/lead",
                    "content": "",
                }
            ],
        )

    def test_position_missing_uid_or_title_is_skipped(self) -> None:
        """Drop malformed entries instead of producing an empty-id record."""

        html_response = MagicMock()
        html_response.text = """
        window.COMPANY_POSITIONS_DATA = [
            {"name": "Valid Role", "uid": "11.111", "location": {}, "custom_fields": {}},
            {"name": "", "uid": "22.222"},
            {"uid": "33.333"},
            {"name": "No UID Role"}
        ];
        """
        company = {"company_id": "example", "api_url": "https://www.comeet.com/jobs/example/1"}

        with patch(
            "scrapers.browser.custom_adapters.requests.get",
            return_value=html_response,
        ):
            jobs = custom_adapters.scrape_comeet(company)

        self.assertEqual([job["id"] for job in jobs], ["example_11.111"])

    def test_request_failure_returns_empty_list(self) -> None:
        """Fail closed instead of raising when the board is unreachable."""

        company = {"company_id": "example", "api_url": "https://www.comeet.com/jobs/example/1"}

        with patch(
            "scrapers.browser.custom_adapters.requests.get",
            side_effect=custom_adapters.requests.RequestException("boom"),
        ):
            jobs = custom_adapters.scrape_comeet(company)

        self.assertEqual(jobs, [])

    def test_missing_company_id_or_api_url_returns_empty_list(self) -> None:
        """Refuse to guess when required configuration is absent."""

        with patch("scrapers.browser.custom_adapters.requests.get") as get:
            self.assertEqual(
                custom_adapters.scrape_comeet({"api_url": "https://x.test"}), []
            )
            self.assertEqual(
                custom_adapters.scrape_comeet({"company_id": "x"}), []
            )
        get.assert_not_called()


if __name__ == "__main__":
    unittest.main()
