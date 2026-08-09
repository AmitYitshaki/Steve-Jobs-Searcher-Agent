"""Tests for evidence-bound LLM job analysis prompts."""

from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")

from analysis.ai.analyzer import (  # noqa: E402
    analyze_job,
    build_job_analysis_prompt,
)


class JobAnalysisPromptTests(unittest.TestCase):
    """Verify prompts distinguish real content from title-only analysis."""

    def test_prompt_contains_real_structured_job_fields(self) -> None:
        """Include factual title, location, and posting content."""

        prompt = build_job_analysis_prompt(
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
        self.assertIn("NEVER use Markdown code blocks", prompt)
        self.assertIn("triple-backtick fences", prompt)
        self.assertIn("<b>תפקיד ומיקום</b>", prompt)
        self.assertNotIn("**", prompt)

    def test_missing_content_requests_explicit_smart_estimation(self) -> None:
        """Estimate from the title while labeling the evidence limitation."""

        prompt = build_job_analysis_prompt(
            job_title="Software Engineer Intern",
            job_location="Haifa, Israel",
            job_content="",
        )

        self.assertIn("NO FULL JOB DESCRIPTION WAS AVAILABLE", prompt)
        self.assertIn(
            "Estimate the typical requirements for this job based solely "
            "on the title",
            prompt,
        )
        self.assertIn(
            "evaluate the user's fit against those estimated requirements",
            prompt,
        )
        self.assertIn(
            "this is an estimation because the full",
            prompt,
        )
        self.assertNotIn(
            "a reliable numeric match percentage cannot be determined",
            prompt,
        )

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
            patch(
                "analysis.ai.analyzer.load_file",
                return_value="context",
            ),
            patch(
                "analysis.ai.analyzer.client.chat.completions.create",
                return_value=response,
            ) as create,
            patch("analysis.ai.analyzer.log_cost", return_value=0.0),
            patch("builtins.print"),
        ):
            result = analyze_job(
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
