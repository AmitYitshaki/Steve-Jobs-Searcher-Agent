"""Tests for evidence-bound LLM job analysis prompts."""

from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")

import main  # noqa: E402


class JobAnalysisPromptTests(unittest.TestCase):
    """Verify prompts distinguish real content from title-only analysis."""

    def test_prompt_contains_real_structured_job_fields(self) -> None:
        """Include factual title, location, and posting content."""

        prompt = main.build_job_analysis_prompt(
            job_title="Student Backend Developer",
            job_location="Tel Aviv, Israel",
            job_content="Build Python APIs. Requires two study semesters.",
        )

        self.assertIn("Student Backend Developer", prompt)
        self.assertIn("Tel Aviv, Israel", prompt)
        self.assertIn("Build Python APIs", prompt)
        self.assertIn("VERIFIED JOB POSTING CONTENT", prompt)
        self.assertNotIn("Full job description available at:", prompt)
        self.assertIn("Return Telegram-compatible HTML", prompt)
        self.assertIn("<b>תפקיד ומיקום</b>", prompt)
        self.assertNotIn("**", prompt)

    def test_missing_content_forbids_invented_requirements(self) -> None:
        """Require title-only output when no description was extracted."""

        prompt = main.build_job_analysis_prompt(
            job_title="Software Engineer Intern",
            job_location="Haifa, Israel",
            job_content="",
        )

        self.assertIn("NO FULL JOB DESCRIPTION WAS AVAILABLE", prompt)
        self.assertIn("Do not infer or invent", prompt)
        self.assertIn("reliable numeric match percentage", prompt)

    def test_analyze_job_sends_the_evidence_bound_prompt(self) -> None:
        """Send the structured prompt without making a live OpenAI call."""

        response = SimpleNamespace(
            usage=SimpleNamespace(
                prompt_tokens=10,
                completion_tokens=5,
            ),
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="analysis")
                )
            ],
        )
        with (
            patch("main.load_file", return_value="context"),
            patch(
                "main.client.chat.completions.create",
                return_value=response,
            ) as create,
            patch("main.log_cost", return_value=0.0),
            patch("builtins.print"),
        ):
            result = main.analyze_job(
                job_title="Student Data Analyst",
                job_location="Jerusalem, Israel",
                job_content=None,
            )

        self.assertEqual(result, "analysis")
        user_message = create.call_args.kwargs["messages"][1]["content"]
        self.assertIn("Student Data Analyst", user_message)
        self.assertIn("NO FULL JOB DESCRIPTION WAS AVAILABLE", user_message)


if __name__ == "__main__":
    unittest.main()
