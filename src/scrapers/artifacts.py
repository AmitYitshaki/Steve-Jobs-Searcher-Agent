"""Write the standard 3-file diagnostic trio for one visited company."""

from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from paths import ARTIFACTS_DIR

LOGGER = logging.getLogger(__name__)

REPLACE_ATTEMPTS = 5
REPLACE_RETRY_DELAY_SECONDS = 0.1

# Redact sensitive query-string values from any text artifact before it is
# written to disk, whether it is rendered HTML or a raw API response body.
SENSITIVE_TEXT_PATTERN = re.compile(
    r"(?i)([?&](?:access_token|api_key|apikey|auth|authorization|"
    r"code|key|session|sessionid|sig|signature|token)=)"
    r"([^&\"'\s<>]+)"
)


def extract_sample_titles(
    jobs: list[Mapping[str, Any]] | None,
    limit: int = 5,
) -> list[str]:
    """Return up to ``limit`` job titles so a run can be sanity-checked."""

    if not jobs:
        return []

    titles: list[str] = []
    for job in jobs:
        if not isinstance(job, Mapping):
            continue
        title = job.get("title")
        if isinstance(title, str) and title.strip():
            titles.append(title.strip())
        if len(titles) >= limit:
            break
    return titles


def _replace_with_retry(temporary_path: Path, destination: Path) -> None:
    """Retry transient Windows file locks during atomic replacement."""

    for attempt in range(1, REPLACE_ATTEMPTS + 1):
        try:
            os.replace(temporary_path, destination)
            return
        except OSError as error:
            is_windows_lock = (
                isinstance(error, PermissionError)
                or getattr(error, "winerror", None) == 5
            )
            if not is_windows_lock or attempt >= REPLACE_ATTEMPTS:
                raise
            time.sleep(REPLACE_RETRY_DELAY_SECONDS)


def _write_text_atomic(destination: Path, text: str) -> None:
    """Write ``text`` to ``destination`` via a same-directory temp file."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = destination.with_suffix(f"{destination.suffix}.tmp")
    with temporary_path.open("w", encoding="utf-8") as handle:
        handle.write(text)
    _replace_with_retry(temporary_path, destination)


def _write_bytes_atomic(destination: Path, data: bytes) -> None:
    """Write ``data`` to ``destination`` via a same-directory temp file."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = destination.with_suffix(f"{destination.suffix}.tmp")
    with temporary_path.open("wb") as handle:
        handle.write(data)
    _replace_with_retry(temporary_path, destination)


def write_company_artifacts(
    company_id: str,
    *,
    source: str,
    primary_content: str | None,
    primary_extension: str,
    screenshot_bytes: bytes | None,
    notes: Mapping[str, Any],
    debug_dir: Path | str = ARTIFACTS_DIR,
) -> tuple[str, ...]:
    """Write the primary artifact, optional screenshot, and notes file.

    Every visited company gets a consistent trio in ``debug_dir``:
    ``{company_id}.{primary_extension}``, ``{company_id}.png`` (only when a
    screenshot was actually captured), and ``{company_id}_diagnostic.json``.
    Each call overwrites the previous run's files for that company; this is
    a current-snapshot artifact set, not a history.

    This is a best-effort diagnostic aid: no failure here (bad input types,
    disk errors, serialization issues) is ever allowed to propagate and
    break the real scrape that called it.
    """

    clean_company_id = company_id.strip()
    if not clean_company_id:
        LOGGER.warning("Skipping artifacts: company_id must be non-empty")
        return ()

    debug_dir_path = Path(debug_dir)
    written_paths: list[str] = []

    if primary_content is not None:
        if isinstance(primary_content, str):
            try:
                sanitized_content = SENSITIVE_TEXT_PATTERN.sub(
                    r"\1[REDACTED]",
                    primary_content,
                )
                primary_path = (
                    debug_dir_path / f"{clean_company_id}.{primary_extension}"
                )
                _write_text_atomic(primary_path, sanitized_content)
                written_paths.append(str(primary_path))
            except OSError as error:
                LOGGER.warning(
                    "Could not write primary artifact for %s: %s",
                    clean_company_id,
                    error,
                )
        else:
            LOGGER.warning(
                "Skipping primary artifact for %s: expected str, got %s",
                clean_company_id,
                type(primary_content).__name__,
            )

    if screenshot_bytes is not None:
        if isinstance(screenshot_bytes, bytes):
            try:
                screenshot_path = debug_dir_path / f"{clean_company_id}.png"
                _write_bytes_atomic(screenshot_path, screenshot_bytes)
                written_paths.append(str(screenshot_path))
            except OSError as error:
                LOGGER.warning(
                    "Could not write screenshot for %s: %s",
                    clean_company_id,
                    error,
                )
        else:
            LOGGER.warning(
                "Skipping screenshot for %s: expected bytes, got %s",
                clean_company_id,
                type(screenshot_bytes).__name__,
            )

    try:
        notes_payload = {
            "company_id": clean_company_id,
            "source": source,
            **dict(notes),
            "captured_at": datetime.now(timezone.utc).isoformat(),
        }
        notes_path = debug_dir_path / f"{clean_company_id}_diagnostic.json"
        _write_text_atomic(
            notes_path,
            json.dumps(notes_payload, ensure_ascii=False, indent=2, default=str),
        )
        written_paths.append(str(notes_path))
    except (OSError, TypeError) as error:
        LOGGER.warning(
            "Could not write diagnostic notes for %s: %s",
            clean_company_id,
            error,
        )

    return tuple(written_paths)
