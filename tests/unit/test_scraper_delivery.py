"""Tests for the Telegram-free scraping producer."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")

from models.results import ScrapeResult, ScrapeStatus  # noqa: E402
from scrapers import orchestrator as scraper  # noqa: E402
from storage.health import ScraperHealthStore  # noqa: E402
from storage.history import JobHistoryStore  # noqa: E402
from storage.queue import PendingAlert, PendingAlertQueue  # noqa: E402


class ScraperProducerTests(unittest.TestCase):
    """Verify relevant jobs are analyzed once and durably queued."""

    COMPANY = {
        "company_id": "example",
        "company_name": "Example",
        "ats_type": "greenhouse",
        "api_url": "https://example.test/jobs",
        "location_filters": ["Israel"],
    }
    JOB = {
        "id": "example_123",
        "title": "Student Software Engineer",
        "location": "Israel",
        "url": "https://example.test/jobs/israel/123",
        "content": "Build Python services. B.Sc. students only.",
    }
    FOREIGN_JOB = {
        "id": "example_456",
        "title": "Student Software Engineer - Budapest, Hungary",
        "location": "Israel",
        "url": "https://example.test/jobs/budapest/456",
        "content": "Build Python services.",
    }
    UNKNOWN_FOREIGN_JOB = {
        "id": "example_789",
        "title": "Student Software Engineer - Valparaiso",
        "location": "Israel",
        "url": "https://example.test/jobs/valparaiso/789",
        "content": "Build Python services.",
    }
    HTML_TITLE_JOB = {
        "id": "example_999",
        "title": "Student Software Engineer <R&D> - Israel",
        "location": "Tel Aviv & Central, Israel",
        "url": (
            "https://example.test/jobs/israel/999"
            "?team=R%26D&level=student"
        ),
        "content": "Build Python services.",
    }

    @staticmethod
    def _successful_result(*jobs: dict[str, str]) -> ScrapeResult:
        """Return one typed successful adapter outcome for producer tests."""

        return ScrapeResult(
            status=ScrapeStatus.SUCCESS,
            jobs=list(jobs),
        )

    def test_title_decision_rejects_non_rd_entry_level_roles(self) -> None:
        """Reject explicit business functions despite internship signals."""

        cases = (
            "Sales Development Representative (SDR - Internship)",
            "Marketing Intern",
            "Human Resources Student",
            "Business Development Intern",
        )

        for title in cases:
            with self.subTest(title=title):
                decision = scraper.is_relevant_job(title)
                self.assertFalse(decision.allowed)
                self.assertEqual(
                    decision.reason,
                    "excluded title keyword",
                )
                self.assertIsNotNone(decision.matched_keyword)

    def test_title_decision_preserves_strong_high_recall_signal(self) -> None:
        """Keep hardware student roles under the high-recall policy."""

        decision = scraper.is_relevant_job("Chip Design Student")

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.reason, "strong entry-level signal")
        self.assertEqual(decision.matched_keyword, "student")

    def test_sdr_hardware_title_is_not_excluded(self) -> None:
        """Do not confuse software-defined radio with a sales role."""

        decision = scraper.is_relevant_job(
            "Software Defined Radio (SDR) Student Engineer"
        )

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.matched_keyword, "student")

    def test_graduate_software_dev_title_is_relevant(self) -> None:
        """Accept Amazon's graduate software-development abbreviation."""

        decision = scraper.is_relevant_job(
            "2026 Graduate Software Dev Engineer"
        )

        self.assertTrue(decision.allowed)
        self.assertEqual(
            decision.reason,
            "weak entry-level and target-role signals",
        )
        self.assertEqual(decision.matched_keyword, "graduate")

    def test_junior_security_roles_are_relevant(self) -> None:
        """Accept explicit junior security roles without internship wording."""

        titles = (
            "Junior Security Engineer",
            "Junior Security Researcher",
            "Junior Penetration Tester",
            "Junior SOC Analyst",
            "Junior Security Analyst",
            "Junior Application Security Engineer",
            "Junior Cyber Security Engineer",
            "Junior Threat Researcher",
            "Junior Incident Response Analyst",
        )

        for title in titles:
            with self.subTest(title=title):
                decision = scraper.is_relevant_job(title)
                self.assertTrue(decision.allowed)
                self.assertEqual(
                    decision.reason,
                    "weak entry-level and target-role signals",
                )

    def test_senior_security_roles_remain_excluded(self) -> None:
        """Keep seniority exclusions stronger than new security role terms."""

        titles = (
            "Senior Security Engineer",
            "Lead Security Researcher",
            "Principal SOC Analyst",
            "Security Engineering Manager",
        )

        for title in titles:
            with self.subTest(title=title):
                decision = scraper.is_relevant_job(title)
                self.assertFalse(decision.allowed)
                self.assertEqual(decision.reason, "excluded title keyword")

    def test_target_role_gate_ignores_seniority(self) -> None:
        """Let catalog research detect target work regardless of seniority."""

        self.assertTrue(
            scraper.matches_target_role("Principal Security Researcher")
        )
        self.assertFalse(scraper.matches_target_role("Jewelry Designer"))

    def test_engineer_one_is_entry_level_but_senior_still_wins(self) -> None:
        """Recognize Engineer I only after higher seniority is excluded."""

        for title in (
            "QA Engineer I",
            "Engineer I-Software Development",
        ):
            with self.subTest(title=title):
                decision = scraper.is_relevant_job(title)
                self.assertTrue(decision.allowed)
                self.assertEqual(
                    decision.reason,
                    "weak entry-level and target-role signals",
                )
                self.assertEqual(decision.matched_keyword, "engineer i")

        senior_decision = scraper.is_relevant_job(
            "Senior Engineer I - Software Development"
        )
        self.assertFalse(senior_decision.allowed)
        self.assertEqual(senior_decision.reason, "excluded title keyword")
        self.assertEqual(senior_decision.matched_keyword, "senior")

    def test_graduate_keyword_has_negative_controls(self) -> None:
        """Avoid substring, seniority, and unrelated-program matches."""

        titles = (
            "Undergraduate Software Engineer",
            "Graduate Program Manager",
            "MBA Graduate Finance Program",
        )

        for title in titles:
            with self.subTest(title=title):
                self.assertFalse(scraper.is_relevant_job(title).allowed)

    def test_target_role_survives_an_exclusion_inside_its_own_name(
        self,
    ) -> None:
        """Accept product roles this config explicitly targets.

        ``TARGET_ROLE_KEYWORDS`` lists these phrases verbatim, but "manager"
        sits in ``EXCLUDE_KEYWORDS``, so the filter used to contradict its own
        target list and reject every one of them.
        """

        cases = (
            ("Product Manager Intern", "intern"),
            ("Student Product Manager", "student"),
            ("Technical Product Manager Intern", "intern"),
        )

        for title, expected_keyword in cases:
            with self.subTest(title=title):
                decision = scraper.is_relevant_job(title)
                self.assertTrue(decision.allowed)
                self.assertEqual(
                    decision.reason,
                    "strong entry-level signal",
                )
                self.assertEqual(decision.matched_keyword, expected_keyword)

    def test_exclusion_outside_the_role_name_still_rejects(self) -> None:
        """Only exclusions contained in a matched role name are forgiven."""

        cases = (
            # "manager" with no target role around it.
            ("Engineering Manager", "manager"),
            ("Product Manager", "manager"),
            # Seniority sits outside the role phrase.
            ("Senior Product Manager", "senior"),
            # A second, unrelated exclusion must still block the title.
            ("Product Manager Intern, Sales", "sales"),
        )

        for title, expected_keyword in cases:
            with self.subTest(title=title):
                decision = scraper.is_relevant_job(title)
                self.assertFalse(decision.allowed)
                self.assertEqual(decision.reason, "excluded title keyword")
                self.assertEqual(decision.matched_keyword, expected_keyword)

    def test_abbreviated_grad_titles_are_recognized(self) -> None:
        """Match "Grad" phrasings that are not prefixes of "graduate"."""

        cases = (
            "Software Engineer, University Grad",
            "Data Analyst Grad Program",
        )

        for title in cases:
            with self.subTest(title=title):
                decision = scraper.is_relevant_job(title)
                self.assertTrue(decision.allowed)
                self.assertEqual(
                    decision.reason,
                    "weak entry-level and target-role signals",
                )

    def test_non_relevant_title_returns_structured_reason(self) -> None:
        """Explain why an otherwise valid title did not qualify."""

        decision = scraper.is_relevant_job("Office Administrator")

        self.assertFalse(decision.allowed)
        self.assertEqual(
            decision.reason,
            "no qualifying entry-level title signal",
        )
        self.assertIsNone(decision.matched_keyword)

    def test_configured_location_filter_fails_closed_on_empty_location(
        self,
    ) -> None:
        """Reject unknown adapter locations when a company requires Israel."""

        self.assertFalse(scraper.is_in_location("", ["Israel"]))
        self.assertFalse(scraper.is_in_location(None, ["Israel"]))
        self.assertTrue(scraper.is_in_location("", []))
        self.assertTrue(
            scraper.is_in_location("Tel Aviv, Israel", ["Israel"])
        )

    def test_israeli_city_location_reaches_candidate_pipeline(self) -> None:
        """Accept a bare Israeli city when the company filter is Israel."""

        tel_aviv_job = {**self.JOB, "location": "Tel Aviv"}
        with tempfile.TemporaryDirectory() as directory:
            queue = PendingAlertQueue(
                Path(directory) / "pending_alerts.json"
            )
            history_store = JobHistoryStore(
                Path(directory) / "jobs_history.json"
            )
            with (
                patch(
                    "scrapers.orchestrator.load_json",
                    side_effect=[[self.COMPANY]],
                ),
                patch(
                    "scrapers.orchestrator.fetch_jobs_from_company",
                    return_value=self._successful_result(tel_aviv_job),
                ),
                patch(
                    "scrapers.orchestrator.analyze_job",
                    return_value="LLM analysis",
                ) as analyze_job,
            ):
                scraper.run_scraper(
                    queue=queue,
                    history_store=history_store,
                    health_store=ScraperHealthStore(
                        Path(directory) / "scraper_health.json"
                    ),
                )

            alerts = queue.load()

        analyze_job.assert_called_once()
        self.assertEqual([alert.job_id for alert in alerts], ["example_123"])

    def test_title_rejection_is_debug_logged_before_analysis(self) -> None:
        """Keep deterministic title rejection detail out of INFO output."""

        sales_job = {
            **self.JOB,
            "title": "Sales Development Representative (SDR - Internship)",
        }
        with tempfile.TemporaryDirectory() as directory:
            queue = PendingAlertQueue(
                Path(directory) / "pending_alerts.json"
            )
            history_store = JobHistoryStore(
                Path(directory) / "jobs_history.json"
            )
            with (
                patch(
                    "scrapers.orchestrator.load_json",
                    side_effect=[[self.COMPANY]],
                ),
                patch(
                    "scrapers.orchestrator.fetch_jobs_from_company",
                    return_value=self._successful_result(sales_job),
                ),
                patch(
                    "scrapers.orchestrator.analyze_job"
                ) as analyze_job,
                patch("scrapers.orchestrator.LOGGER.debug") as debug,
            ):
                scraper.run_scraper(
                    queue=queue,
                    history_store=history_store,
                    health_store=ScraperHealthStore(
                        Path(directory) / "scraper_health.json"
                    ),
                )

            alerts = queue.load()

        self.assertEqual(alerts, [])
        analyze_job.assert_not_called()
        self.assertTrue(
            any(
                call_args.args[0].startswith("Rejecting %s: title")
                for call_args in debug.call_args_list
            )
        )

    def test_new_job_is_analyzed_and_queued(self) -> None:
        """Store all required fields without invoking Telegram."""

        with tempfile.TemporaryDirectory() as directory:
            queue = PendingAlertQueue(
                Path(directory) / "pending_alerts.json"
            )
            history_store = JobHistoryStore(
                Path(directory) / "jobs_history.json"
            )
            with (
                patch(
                    "scrapers.orchestrator.load_json",
                    side_effect=[[self.COMPANY]],
                ),
                patch(
                    "scrapers.orchestrator.fetch_jobs_from_company",
                    return_value=self._successful_result(self.JOB),
                ),
                patch(
                    "scrapers.orchestrator.analyze_job",
                    return_value="LLM analysis",
                ) as analyze_job,
                patch("builtins.print"),
            ):
                scraper.run_scraper(
                    queue=queue,
                    history_store=history_store,
                    health_store=ScraperHealthStore(
                        Path(directory) / "scraper_health.json"
                    ),
                )

            alerts = queue.load()

        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].job_id, "example_123")
        self.assertEqual(alerts[0].company_name, "Example")
        self.assertEqual(
            alerts[0].job_url,
            "https://example.test/jobs/israel/123",
        )
        self.assertIn("LLM analysis", alerts[0].llm_summary)
        self.assertIn("Student Software Engineer", alerts[0].llm_summary)
        analyze_job.assert_called_once_with(
            job_title="Student Software Engineer",
            job_location="Israel",
            job_content="Build Python services. B.Sc. students only.",
        )

    def test_alert_header_uses_safe_html_formatting(self) -> None:
        """Bold the header while escaping title and location text."""

        with tempfile.TemporaryDirectory() as directory:
            queue = PendingAlertQueue(
                Path(directory) / "pending_alerts.json"
            )
            history_store = JobHistoryStore(
                Path(directory) / "jobs_history.json"
            )
            html_company = {
                **self.COMPANY,
                "company_name": "Example <Labs> & Co",
            }
            with (
                patch(
                    "scrapers.orchestrator.load_json",
                    side_effect=[[html_company]],
                ),
                patch(
                    "scrapers.orchestrator.fetch_jobs_from_company",
                    return_value=self._successful_result(
                        self.HTML_TITLE_JOB
                    ),
                ),
                patch(
                    "scrapers.orchestrator.analyze_job",
                    return_value="<b>ניתוח</b>",
                ),
                patch("builtins.print"),
            ):
                scraper.run_scraper(
                    queue=queue,
                    history_store=history_store,
                    health_store=ScraperHealthStore(
                        Path(directory) / "scraper_health.json"
                    ),
                )

            summary = queue.load()[0].llm_summary

        self.assertIn(
            "<b>משרה חדשה נמצאה: Student Software Engineer "
            "&lt;R&amp;D&gt; - Israel</b>",
            summary,
        )
        self.assertIn(
            "🏢 חברה: Example &lt;Labs&gt; &amp; Co",
            summary,
        )
        self.assertIn("Tel Aviv &amp; Central, Israel", summary)
        self.assertIn(
            "🔗 קישור: https://example.test/jobs/israel/999"
            "?team=R%26D&amp;level=student",
            summary,
        )
        self.assertIn("<b>ניתוח</b>", summary)
        self.assertNotIn("**", summary)

    def test_pending_job_is_not_analyzed_again(self) -> None:
        """Avoid repeat LLM cost while an alert is waiting for delivery."""

        with tempfile.TemporaryDirectory() as directory:
            queue = PendingAlertQueue(
                Path(directory) / "pending_alerts.json"
            )
            history_store = JobHistoryStore(
                Path(directory) / "jobs_history.json"
            )
            queue.append(
                PendingAlert(
                    job_id="example_123",
                    company_name="Example",
                    job_url="https://example.test/jobs/123",
                    llm_summary="Already analyzed",
                )
            )
            with (
                patch(
                    "scrapers.orchestrator.load_json",
                    side_effect=[[self.COMPANY]],
                ),
                patch(
                    "scrapers.orchestrator.fetch_jobs_from_company",
                    return_value=self._successful_result(self.JOB),
                ),
                patch(
                    "scrapers.orchestrator.analyze_job"
                ) as analyze_job,
                patch("builtins.print"),
            ):
                scraper.run_scraper(
                    queue=queue,
                    history_store=history_store,
                    health_store=ScraperHealthStore(
                        Path(directory) / "scraper_health.json"
                    ),
                )

            alerts = queue.load()

        analyze_job.assert_not_called()
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].llm_summary, "Already analyzed")

    def test_cycle_saves_company_health_with_duplicate_visibility(self) -> None:
        """Persist one health snapshot after the complete company cycle."""

        sales_job = {
            **self.JOB,
            "id": "example_sales",
            "title": "Sales Intern",
        }
        with tempfile.TemporaryDirectory() as directory:
            queue = PendingAlertQueue(
                Path(directory) / "pending_alerts.json"
            )
            history_store = JobHistoryStore(
                Path(directory) / "jobs_history.json"
            )
            queue.append(
                PendingAlert(
                    job_id=self.JOB["id"],
                    company_name="Example",
                    job_url=self.JOB["url"],
                    llm_summary="Already analyzed",
                )
            )
            health_store = MagicMock()
            health_store.load.return_value = {}
            with (
                patch(
                    "scrapers.orchestrator.load_json",
                    side_effect=[[self.COMPANY]],
                ),
                patch(
                    "scrapers.orchestrator.fetch_jobs_from_company",
                    return_value=self._successful_result(
                        self.JOB,
                        sales_job,
                        self.FOREIGN_JOB,
                    ),
                ),
                patch(
                    "scrapers.orchestrator.analyze_job"
                ) as analyze_job,
                patch("scrapers.orchestrator.LOGGER.info") as info,
            ):
                scraper.run_scraper(
                    queue=queue,
                    history_store=history_store,
                    health_store=health_store,
                )

        analyze_job.assert_not_called()
        health_store.save.assert_called_once()
        saved_state = health_store.save.call_args.args[0]["example"]
        self.assertEqual(saved_state["last_job_count"], 3)
        self.assertEqual(saved_state["last_relevant_job_count"], 1)
        self.assertEqual(saved_state["last_duplicate_job_count"], 1)
        self.assertEqual(saved_state["last_title_rejection_count"], 1)
        self.assertEqual(saved_state["last_location_rejection_count"], 1)
        self.assertEqual(saved_state["last_status"], "healthy")
        self.assertTrue(
            any(
                "1 duplicates" in str(call_args)
                for call_args in info.call_args_list
            )
        )

    def test_waf_block_is_recorded_as_failure_not_zero_job_run(self) -> None:
        """Keep typed hard failures out of silent-zero anomaly counters."""

        with tempfile.TemporaryDirectory() as directory:
            health_store = MagicMock()
            health_store.load.return_value = {
                "example": {
                    "last_success_at": "2026-09-20T10:00:00+00:00",
                    "consecutive_failures": 1,
                    "consecutive_zero_job_runs": 2,
                    "job_count_history": [4, 3],
                }
            }
            with (
                patch(
                    "scrapers.orchestrator.load_json",
                    side_effect=[[self.COMPANY]],
                ),
                patch(
                    "scrapers.orchestrator.fetch_jobs_from_company",
                    return_value=ScrapeResult(
                        status=ScrapeStatus.WAF_BLOCKED,
                        jobs=[],
                        message="HTTP 403",
                    ),
                ),
                patch("scrapers.orchestrator.analyze_job") as analyze_job,
            ):
                scraper.run_scraper(
                    queue=PendingAlertQueue(
                        Path(directory) / "pending_alerts.json"
                    ),
                    history_store=JobHistoryStore(
                        Path(directory) / "jobs_history.json"
                    ),
                    health_store=health_store,
                )

        analyze_job.assert_not_called()
        saved_state = health_store.save.call_args.args[0]["example"]
        self.assertEqual(saved_state["last_status"], "failed")
        self.assertEqual(saved_state["consecutive_failures"], 2)
        self.assertEqual(saved_state["consecutive_zero_job_runs"], 2)
        self.assertEqual(saved_state["job_count_history"], [4, 3])
        self.assertEqual(saved_state["last_error_type"], "WAF_BLOCKED")

    def test_foreign_similar_job_is_rejected_before_analysis(self) -> None:
        """Drop a geographic leak even when its adapter says Israel."""

        with tempfile.TemporaryDirectory() as directory:
            queue = PendingAlertQueue(
                Path(directory) / "pending_alerts.json"
            )
            history_store = JobHistoryStore(
                Path(directory) / "jobs_history.json"
            )
            with (
                patch(
                    "scrapers.orchestrator.load_json",
                    side_effect=[[self.COMPANY]],
                ),
                patch(
                    "scrapers.orchestrator.fetch_jobs_from_company",
                    return_value=self._successful_result(
                        self.FOREIGN_JOB
                    ),
                ),
                patch(
                    "scrapers.orchestrator.analyze_job"
                ) as analyze_job,
                patch("scrapers.orchestrator.LOGGER.debug") as debug,
                patch("scrapers.orchestrator.LOGGER.info") as info,
            ):
                scraper.run_scraper(
                    queue=queue,
                    history_store=history_store,
                    health_store=ScraperHealthStore(
                        Path(directory) / "scraper_health.json"
                    ),
                )

            alerts = queue.load()

        analyze_job.assert_not_called()
        self.assertEqual(alerts, [])
        self.assertTrue(
            any(
                "Budapest" in str(call_args)
                for call_args in debug.call_args_list
            )
        )
        self.assertFalse(
            any(
                "Budapest" in str(call_args)
                for call_args in info.call_args_list
            )
        )

    def test_unknown_location_is_allowed_in_medium_mode(self) -> None:
        """Allow unknown locations unless the blacklist identifies them."""

        with tempfile.TemporaryDirectory() as directory:
            queue = PendingAlertQueue(
                Path(directory) / "pending_alerts.json"
            )
            history_store = JobHistoryStore(
                Path(directory) / "jobs_history.json"
            )
            with (
                patch(
                    "scrapers.orchestrator.load_json",
                    side_effect=[[self.COMPANY]],
                ),
                patch(
                    "scrapers.orchestrator.fetch_jobs_from_company",
                    return_value=self._successful_result(
                        self.UNKNOWN_FOREIGN_JOB
                    ),
                ),
                patch(
                    "scrapers.orchestrator.analyze_job",
                    return_value="LLM analysis",
                ) as analyze_job,
                patch("builtins.print"),
            ):
                scraper.run_scraper(
                    queue=queue,
                    history_store=history_store,
                    health_store=ScraperHealthStore(
                        Path(directory) / "scraper_health.json"
                    ),
                )

            alerts = queue.load()

        analyze_job.assert_called_once_with(
            job_title="Student Software Engineer - Valparaiso",
            job_location="Israel",
            job_content="Build Python services.",
        )
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].job_id, "example_789")


    def test_health_digest_sent_when_company_enters_anomaly(self) -> None:
        """Report one company crossing from healthy into failed."""

        notifier = MagicMock()
        with tempfile.TemporaryDirectory() as directory:
            health_store = MagicMock()
            health_store.load.return_value = {
                "example": {
                    "company_name": "Example",
                    "last_success_at": "2026-09-20T10:00:00+00:00",
                    "last_status": "healthy",
                    "consecutive_failures": 2,
                    "consecutive_zero_job_runs": 0,
                    "job_count_history": [3],
                }
            }
            with (
                patch(
                    "scrapers.orchestrator.load_json",
                    side_effect=[[self.COMPANY]],
                ),
                patch(
                    "scrapers.orchestrator.fetch_jobs_from_company",
                    return_value=ScrapeResult(
                        status=ScrapeStatus.WAF_BLOCKED,
                        jobs=[],
                        message="HTTP 403",
                    ),
                ),
                patch("scrapers.orchestrator.analyze_job"),
            ):
                scraper.run_scraper(
                    queue=PendingAlertQueue(
                        Path(directory) / "pending_alerts.json"
                    ),
                    history_store=JobHistoryStore(
                        Path(directory) / "jobs_history.json"
                    ),
                    health_store=health_store,
                    heartbeat_notifier=notifier,
                )

        notifier.send.assert_any_call(
            "Scraper health changes:\n"
            "🚨 Example: healthy -> failed | error=WAF_BLOCKED | "
            "consecutive failures=3"
        )

    def test_health_digest_explains_degraded_zero_job_anomaly(self) -> None:
        """Include the silent-breakage counter for a degraded company."""

        notifier = MagicMock()
        with tempfile.TemporaryDirectory() as directory:
            health_store = MagicMock()
            health_store.load.return_value = {
                "example": {
                    "company_name": "Example",
                    "last_success_at": "2026-09-20T10:00:00+00:00",
                    "last_status": "healthy",
                    "consecutive_failures": 0,
                    "consecutive_zero_job_runs": 2,
                    "job_count_history": [3, 0, 0],
                }
            }
            with (
                patch(
                    "scrapers.orchestrator.load_json",
                    side_effect=[[self.COMPANY]],
                ),
                patch(
                    "scrapers.orchestrator.fetch_jobs_from_company",
                    return_value=ScrapeResult(
                        status=ScrapeStatus.NO_JOBS,
                        jobs=[],
                    ),
                ),
                patch("scrapers.orchestrator.analyze_job"),
            ):
                scraper.run_scraper(
                    queue=PendingAlertQueue(
                        Path(directory) / "pending_alerts.json"
                    ),
                    history_store=JobHistoryStore(
                        Path(directory) / "jobs_history.json"
                    ),
                    health_store=health_store,
                    heartbeat_notifier=notifier,
                )

        notifier.send.assert_any_call(
            "Scraper health changes:\n"
            "🚨 Example: healthy -> degraded | "
            "consecutive zero-job runs=3"
        )

    def test_health_digest_sent_when_company_recovers(self) -> None:
        """Report a company returning from failed to healthy."""

        notifier = MagicMock()
        with tempfile.TemporaryDirectory() as directory:
            health_store = MagicMock()
            health_store.load.return_value = {
                "example": {
                    "company_name": "Example",
                    "last_success_at": "2026-09-20T10:00:00+00:00",
                    "last_status": "failed",
                    "consecutive_failures": 3,
                    "consecutive_zero_job_runs": 0,
                    "job_count_history": [3],
                    "last_error_type": "WAF_BLOCKED",
                }
            }
            with (
                patch(
                    "scrapers.orchestrator.load_json",
                    side_effect=[[self.COMPANY]],
                ),
                patch(
                    "scrapers.orchestrator.fetch_jobs_from_company",
                    return_value=ScrapeResult(
                        status=ScrapeStatus.NO_JOBS,
                        jobs=[],
                    ),
                ),
                patch("scrapers.orchestrator.analyze_job"),
            ):
                scraper.run_scraper(
                    queue=PendingAlertQueue(
                        Path(directory) / "pending_alerts.json"
                    ),
                    history_store=JobHistoryStore(
                        Path(directory) / "jobs_history.json"
                    ),
                    health_store=health_store,
                    heartbeat_notifier=notifier,
                )

        notifier.send.assert_any_call(
            "Scraper health changes:\n"
            "✅ Example: recovered (failed -> healthy)"
        )

    def test_health_digest_not_sent_when_status_is_unchanged(self) -> None:
        """Keep a stable healthy company out of the operational digest."""

        notifier = MagicMock()
        with tempfile.TemporaryDirectory() as directory:
            health_store = MagicMock()
            health_store.load.return_value = {
                "example": {
                    "company_name": "Example",
                    "last_success_at": "2026-09-20T10:00:00+00:00",
                    "last_status": "healthy",
                    "consecutive_failures": 0,
                    "consecutive_zero_job_runs": 0,
                    "job_count_history": [3],
                }
            }
            with (
                patch(
                    "scrapers.orchestrator.load_json",
                    side_effect=[[self.COMPANY]],
                ),
                patch(
                    "scrapers.orchestrator.fetch_jobs_from_company",
                    return_value=ScrapeResult(
                        status=ScrapeStatus.NO_JOBS,
                        jobs=[],
                    ),
                ),
                patch("scrapers.orchestrator.analyze_job"),
            ):
                scraper.run_scraper(
                    queue=PendingAlertQueue(
                        Path(directory) / "pending_alerts.json"
                    ),
                    history_store=JobHistoryStore(
                        Path(directory) / "jobs_history.json"
                    ),
                    health_store=health_store,
                    heartbeat_notifier=notifier,
                )

        notifier.send.assert_called_once_with(scraper.HEARTBEAT_MESSAGE)

    def test_health_digest_does_not_repeat_standing_anomaly(self) -> None:
        """Do not repeat a failed company on consecutive producer runs."""

        notifier = MagicMock()
        with tempfile.TemporaryDirectory() as directory:
            health_store = MagicMock()
            health_store.load.return_value = {
                "example": {
                    "company_name": "Example",
                    "last_success_at": "2026-09-20T10:00:00+00:00",
                    "last_status": "failed",
                    "consecutive_failures": 3,
                    "consecutive_zero_job_runs": 0,
                    "job_count_history": [3],
                    "last_error_type": "WAF_BLOCKED",
                }
            }
            with (
                patch(
                    "scrapers.orchestrator.load_json",
                    side_effect=[[self.COMPANY], [self.COMPANY]],
                ),
                patch(
                    "scrapers.orchestrator.fetch_jobs_from_company",
                    return_value=ScrapeResult(
                        status=ScrapeStatus.WAF_BLOCKED,
                        jobs=[],
                        message="HTTP 403",
                    ),
                ),
                patch("scrapers.orchestrator.analyze_job"),
            ):
                for _ in range(2):
                    scraper.run_scraper(
                        queue=PendingAlertQueue(
                            Path(directory) / "pending_alerts.json"
                        ),
                        history_store=JobHistoryStore(
                            Path(directory) / "jobs_history.json"
                        ),
                        health_store=health_store,
                        heartbeat_notifier=notifier,
                    )

        sent_messages = [entry.args[0] for entry in notifier.send.call_args_list]
        self.assertEqual(
            sent_messages,
            [scraper.HEARTBEAT_MESSAGE, scraper.HEARTBEAT_MESSAGE],
        )

    def test_health_digest_suppresses_first_run_without_baseline(self) -> None:
        """Avoid catalog-expansion noise when no prior state exists."""

        notifier = MagicMock()
        with tempfile.TemporaryDirectory() as directory:
            health_store = MagicMock()
            health_store.load.return_value = {}
            with (
                patch(
                    "scrapers.orchestrator.load_json",
                    side_effect=[[self.COMPANY]],
                ),
                patch(
                    "scrapers.orchestrator.fetch_jobs_from_company",
                    return_value=ScrapeResult(
                        status=ScrapeStatus.WAF_BLOCKED,
                        jobs=[],
                        message="HTTP 403",
                    ),
                ),
                patch("scrapers.orchestrator.analyze_job"),
            ):
                scraper.run_scraper(
                    queue=PendingAlertQueue(
                        Path(directory) / "pending_alerts.json"
                    ),
                    history_store=JobHistoryStore(
                        Path(directory) / "jobs_history.json"
                    ),
                    health_store=health_store,
                    heartbeat_notifier=notifier,
                )

        notifier.send.assert_called_once_with(scraper.HEARTBEAT_MESSAGE)

    def test_health_digest_combines_all_transitions_in_one_message(self) -> None:
        """Send one digest even when multiple companies change state."""

        recovered_company = {
            **self.COMPANY,
            "company_id": "recovered",
            "company_name": "Recovered Co",
        }
        notifier = MagicMock()
        with tempfile.TemporaryDirectory() as directory:
            health_store = MagicMock()
            health_store.load.return_value = {
                "example": {
                    "company_name": "Example",
                    "last_success_at": "2026-09-20T10:00:00+00:00",
                    "last_status": "healthy",
                    "consecutive_failures": 2,
                    "consecutive_zero_job_runs": 0,
                    "job_count_history": [3],
                },
                "recovered": {
                    "company_name": "Recovered Co",
                    "last_success_at": "2026-09-20T10:00:00+00:00",
                    "last_status": "degraded",
                    "consecutive_failures": 0,
                    "consecutive_zero_job_runs": 3,
                    "job_count_history": [3, 0, 0, 0],
                },
            }
            with (
                patch(
                    "scrapers.orchestrator.load_json",
                    side_effect=[[self.COMPANY, recovered_company]],
                ),
                patch(
                    "scrapers.orchestrator.fetch_jobs_from_company",
                    side_effect=[
                        ScrapeResult(
                            status=ScrapeStatus.WAF_BLOCKED,
                            jobs=[],
                            message="HTTP 403",
                        ),
                        self._successful_result(self.JOB),
                    ],
                ),
                patch(
                    "scrapers.orchestrator.analyze_job",
                    return_value="LLM analysis",
                ),
            ):
                scraper.run_scraper(
                    queue=PendingAlertQueue(
                        Path(directory) / "pending_alerts.json"
                    ),
                    history_store=JobHistoryStore(
                        Path(directory) / "jobs_history.json"
                    ),
                    health_store=health_store,
                    heartbeat_notifier=notifier,
                )

        notifier.send.assert_called_once_with(
            "Scraper health changes:\n"
            "🚨 Example: healthy -> failed | error=WAF_BLOCKED | "
            "consecutive failures=3\n"
            "✅ Recovered Co: recovered (degraded -> healthy)"
        )

    def test_heartbeat_sent_when_no_new_jobs(self) -> None:
        """Emit the heartbeat so a quiet, successful run is never silent."""

        notifier = MagicMock()
        with tempfile.TemporaryDirectory() as directory:
            queue = PendingAlertQueue(
                Path(directory) / "pending_alerts.json"
            )
            history_store = JobHistoryStore(
                Path(directory) / "jobs_history.json"
            )
            with (
                patch(
                    "scrapers.orchestrator.load_json",
                    side_effect=[[self.COMPANY]],
                ),
                patch(
                    "scrapers.orchestrator.fetch_jobs_from_company",
                    return_value=ScrapeResult(
                        status=ScrapeStatus.NO_JOBS,
                        jobs=[],
                    ),
                ),
                patch(
                    "scrapers.orchestrator.analyze_job"
                ) as analyze_job,
                patch("builtins.print"),
            ):
                scraper.run_scraper(
                    queue=queue,
                    history_store=history_store,
                    health_store=ScraperHealthStore(
                        Path(directory) / "scraper_health.json"
                    ),
                    heartbeat_notifier=notifier,
                )

        analyze_job.assert_not_called()
        notifier.send.assert_called_once_with(
            "Scraping cycle completed. 0 new jobs found."
        )

    def test_heartbeat_not_sent_when_new_jobs_found(self) -> None:
        """Stay silent on the heartbeat channel when real jobs were queued."""

        notifier = MagicMock()
        with tempfile.TemporaryDirectory() as directory:
            queue = PendingAlertQueue(
                Path(directory) / "pending_alerts.json"
            )
            history_store = JobHistoryStore(
                Path(directory) / "jobs_history.json"
            )
            with (
                patch(
                    "scrapers.orchestrator.load_json",
                    side_effect=[[self.COMPANY]],
                ),
                patch(
                    "scrapers.orchestrator.fetch_jobs_from_company",
                    return_value=self._successful_result(self.JOB),
                ),
                patch(
                    "scrapers.orchestrator.analyze_job",
                    return_value="LLM analysis",
                ),
                patch("builtins.print"),
            ):
                scraper.run_scraper(
                    queue=queue,
                    history_store=history_store,
                    health_store=ScraperHealthStore(
                        Path(directory) / "scraper_health.json"
                    ),
                    heartbeat_notifier=notifier,
                )

        notifier.send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
