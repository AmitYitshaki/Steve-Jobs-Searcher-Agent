"""Shared typed outcomes returned by job scrapers."""

from dataclasses import dataclass
from enum import Enum

from models.job import JobRecord


class ScrapeStatus(str, Enum):
    """Represent the outcome of one browser scrape."""

    SUCCESS = "success"
    NO_JOBS = "no_jobs"
    WAF_BLOCKED = "waf_blocked"
    FAILED = "failed"


@dataclass(frozen=True)
class ScrapeResult:
    """Return jobs together with an explicit browser scrape outcome."""

    status: ScrapeStatus
    jobs: list[JobRecord]
    message: str = ""
    diagnostic_paths: tuple[str, ...] = ()
