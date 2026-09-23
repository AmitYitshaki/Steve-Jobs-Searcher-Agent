"""Shared console+file logging setup used by every entry-point module."""

from __future__ import annotations

import logging
import os

from paths import LOGS_DIR


def configure_logging() -> None:
    """Log to the console, and additionally to ``PIPELINE_LOG_FILE`` when set.

    ``pipeline.py`` sets this environment variable once per end-to-end run so
    the producer and consumer subprocesses it launches append to the same
    timestamped file under ``logs/`` instead of only printing to the console.
    A standalone module run (``python -m scrapers.orchestrator``) or the
    Docker scheduler leaves it unset and keeps prior console-only behavior.
    """

    handlers: list[logging.Handler] = [logging.StreamHandler()]
    log_file = os.environ.get("PIPELINE_LOG_FILE")
    if log_file:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=handlers,
        force=True,
    )
