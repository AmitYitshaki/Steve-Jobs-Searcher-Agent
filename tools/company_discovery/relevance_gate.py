"""Apply the mandatory target-role gate to company-discovery job samples.

This tool deliberately ignores seniority. Its question is whether an employer
has at least one software-adjacent role at all, not whether a particular job
should be sent to the candidate feed. Runtime alert filtering remains in
``scrapers.orchestrator.is_relevant_job``.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from scrapers.orchestrator import matches_target_role


@dataclass(frozen=True)
class RelevanceGateResult:
    """Summarize whether sampled jobs prove catalog relevance."""

    passed: bool
    matching_titles: tuple[str, ...]


class CatalogRelevanceGate:
    """Evaluate fetched jobs against the shared target-role vocabulary."""

    def evaluate(
        self,
        jobs: Iterable[Mapping[str, Any]],
    ) -> RelevanceGateResult:
        """Return all target-role titles and whether at least one exists."""

        matching_titles = tuple(
            title
            for job in jobs
            if (title := str(job.get("title") or "").strip())
            and matches_target_role(title)
        )
        return RelevanceGateResult(
            passed=bool(matching_titles),
            matching_titles=matching_titles,
        )


def _load_jobs(path: Path) -> list[Mapping[str, Any]]:
    """Load a job list or a ``{"jobs": [...]}`` verification artifact."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    jobs = payload.get("jobs") if isinstance(payload, Mapping) else payload
    if not isinstance(jobs, list) or not all(
        isinstance(job, Mapping) for job in jobs
    ):
        raise ValueError(
            "Expected a JSON job list or an object containing a job list"
        )
    return jobs


def main(argv: Sequence[str] | None = None) -> int:
    """Run the gate for a saved live-verification artifact."""

    parser = argparse.ArgumentParser(
        description=(
            "Require at least one TARGET_ROLE_KEYWORDS/HEBREW_ROLE_KEYWORDS "
            "match before activating a company."
        )
    )
    parser.add_argument("jobs_json", type=Path)
    args = parser.parse_args(argv)

    result = CatalogRelevanceGate().evaluate(_load_jobs(args.jobs_json))
    if not result.passed:
        print("HOLD: no target-role title found")
        return 1

    print(f"PASS: {len(result.matching_titles)} target-role title(s)")
    for title in result.matching_titles:
        print(f"- {title}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
