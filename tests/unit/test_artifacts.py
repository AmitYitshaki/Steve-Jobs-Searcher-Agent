"""Tests for the shared per-company diagnostic artifact writer."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scrapers.artifacts import extract_sample_titles, write_company_artifacts


class WriteCompanyArtifactsTests(unittest.TestCase):
    """Verify the HTML/screenshot/notes trio written per visited company."""

    def test_browser_source_writes_all_three_files(self) -> None:
        """Write HTML, screenshot, and notes when a page was rendered."""

        with tempfile.TemporaryDirectory() as directory:
            paths = write_company_artifacts(
                "google",
                source="browser",
                primary_content="<html>jobs</html>",
                primary_extension="html",
                screenshot_bytes=b"\x89PNG fake bytes",
                notes={"status": "success", "job_count": 3},
                debug_dir=directory,
            )

            html_path = Path(directory) / "google.html"
            screenshot_path = Path(directory) / "google.png"
            notes_path = Path(directory) / "google_diagnostic.json"

            self.assertTrue(html_path.exists())
            self.assertTrue(screenshot_path.exists())
            self.assertTrue(notes_path.exists())
            self.assertEqual(
                set(paths),
                {str(html_path), str(screenshot_path), str(notes_path)},
            )
            self.assertEqual(
                html_path.read_text(encoding="utf-8"),
                "<html>jobs</html>",
            )
            self.assertEqual(screenshot_path.read_bytes(), b"\x89PNG fake bytes")

            notes = json.loads(notes_path.read_text(encoding="utf-8"))
            self.assertEqual(notes["company_id"], "google")
            self.assertEqual(notes["source"], "browser")
            self.assertEqual(notes["status"], "success")
            self.assertEqual(notes["job_count"], 3)
            self.assertIn("captured_at", notes)

    def test_api_source_skips_screenshot_without_a_placeholder(self) -> None:
        """Never fabricate a screenshot when no page was ever rendered."""

        with tempfile.TemporaryDirectory() as directory:
            paths = write_company_artifacts(
                "iai",
                source="api",
                primary_content='{"jobs": []}',
                primary_extension="json",
                screenshot_bytes=None,
                notes={"status": "no_jobs", "job_count": 0},
                debug_dir=directory,
            )

            json_path = Path(directory) / "iai.json"
            screenshot_path = Path(directory) / "iai.png"
            notes_path = Path(directory) / "iai_diagnostic.json"

            self.assertTrue(json_path.exists())
            self.assertFalse(screenshot_path.exists())
            self.assertTrue(notes_path.exists())
            self.assertEqual(set(paths), {str(json_path), str(notes_path)})

            notes = json.loads(notes_path.read_text(encoding="utf-8"))
            self.assertEqual(notes["source"], "api")

    def test_redacts_sensitive_query_values_in_primary_content(self) -> None:
        """Strip token-like query values from HTML and API bodies alike."""

        with tempfile.TemporaryDirectory() as directory:
            write_company_artifacts(
                "meta",
                source="api",
                primary_content=(
                    "https://example.test/jobs?access_token=SECRET123&x=1"
                ),
                primary_extension="json",
                screenshot_bytes=None,
                notes={},
                debug_dir=directory,
            )

            content = (Path(directory) / "meta.json").read_text(
                encoding="utf-8"
            )
            self.assertNotIn("SECRET123", content)
            self.assertIn("access_token=[REDACTED]", content)

    def test_overwrites_previous_run_instead_of_accumulating_history(self) -> None:
        """Keep exactly one current-snapshot trio per company."""

        with tempfile.TemporaryDirectory() as directory:
            write_company_artifacts(
                "rafael",
                source="browser",
                primary_content="<html>first run</html>",
                primary_extension="html",
                screenshot_bytes=b"first",
                notes={"job_count": 1},
                debug_dir=directory,
            )
            write_company_artifacts(
                "rafael",
                source="browser",
                primary_content="<html>second run</html>",
                primary_extension="html",
                screenshot_bytes=b"second",
                notes={"job_count": 2},
                debug_dir=directory,
            )

            html_files = list(Path(directory).glob("rafael*.html"))
            self.assertEqual(len(html_files), 1)
            self.assertEqual(
                html_files[0].read_text(encoding="utf-8"),
                "<html>second run</html>",
            )

    def test_malformed_primary_content_does_not_crash_the_caller(self) -> None:
        """Never let a bad diagnostic input break the real scrape."""

        with tempfile.TemporaryDirectory() as directory:
            paths = write_company_artifacts(
                "example",
                source="api",
                primary_content=object(),  # not a str
                primary_extension="json",
                screenshot_bytes="not-bytes-either",
                notes={"status": "success"},
                debug_dir=directory,
            )

            notes_path = Path(directory) / "example_diagnostic.json"
            self.assertTrue(notes_path.exists())
            self.assertEqual(paths, (str(notes_path),))
            self.assertFalse(
                (Path(directory) / "example.json").exists()
            )
            self.assertFalse(
                (Path(directory) / "example.png").exists()
            )

    def test_blank_company_id_is_skipped_without_raising(self) -> None:
        """Degrade gracefully instead of crashing on bad input."""

        with tempfile.TemporaryDirectory() as directory:
            paths = write_company_artifacts(
                "   ",
                source="api",
                primary_content="{}",
                primary_extension="json",
                screenshot_bytes=None,
                notes={},
                debug_dir=directory,
            )

        self.assertEqual(paths, ())


class ExtractSampleTitlesTests(unittest.TestCase):
    """Verify the notes-file sample-title helper."""

    def test_returns_first_titles_up_to_the_limit(self) -> None:
        """Cap the sample at the configured limit."""

        jobs = [{"title": f"Job {i}"} for i in range(10)]

        self.assertEqual(
            extract_sample_titles(jobs, limit=3),
            ["Job 0", "Job 1", "Job 2"],
        )

    def test_skips_blank_or_missing_titles(self) -> None:
        """Ignore malformed job entries instead of raising."""

        jobs = [
            {"title": ""},
            {"no_title_field": True},
            {"title": "  Real Title  "},
        ]

        self.assertEqual(extract_sample_titles(jobs), ["Real Title"])

    def test_empty_or_none_job_list_returns_empty(self) -> None:
        """Handle the no-jobs case without raising."""

        self.assertEqual(extract_sample_titles(None), [])
        self.assertEqual(extract_sample_titles([]), [])


if __name__ == "__main__":
    unittest.main()
