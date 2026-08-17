"""Atomic JSON persistence with bounded Windows lock retries."""

from __future__ import annotations

import json
import os
import tempfile
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Callable

SleepFunction = Callable[[float], None]


class _AtomicJsonStore:
    """Share atomic file replacement across typed JSON containers."""

    def __init__(
        self,
        path: str | Path,
        replace_attempts: int = 5,
        initial_retry_delay_seconds: float = 0.1,
        max_retry_delay_seconds: float = 0.5,
        sleep_function: SleepFunction = time.sleep,
    ) -> None:
        """Configure atomic storage and bounded Windows lock retries."""

        if replace_attempts < 1:
            raise ValueError("replace_attempts must be at least 1")
        if initial_retry_delay_seconds < 0:
            raise ValueError(
                "initial_retry_delay_seconds cannot be negative"
            )
        if max_retry_delay_seconds < initial_retry_delay_seconds:
            raise ValueError(
                "max_retry_delay_seconds cannot be below the initial delay"
            )
        self.path = Path(path)
        self.replace_attempts = replace_attempts
        self.initial_retry_delay_seconds = initial_retry_delay_seconds
        self.max_retry_delay_seconds = max_retry_delay_seconds
        self.sleep_function = sleep_function

    def _read_json(self, missing_value: Any) -> Any:
        """Decode the JSON file or return the supplied missing-file value."""

        if not self.path.exists():
            return missing_value

        with open(self.path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    def _write_json(self, value: Any) -> None:
        """Write a closed temporary file, then atomically replace the target."""

        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            file_descriptor, temporary_name = tempfile.mkstemp(
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
            )
            os.close(file_descriptor)
            temporary_path = Path(temporary_name)

            with open(temporary_path, "w", encoding="utf-8") as handle:
                json.dump(
                    value,
                    handle,
                    ensure_ascii=False,
                    indent=2,
                )
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())

            # The temporary-file handle is closed before Windows is asked to
            # replace the destination.
            self._replace_with_retry(temporary_path)
        finally:
            if temporary_path is not None and temporary_path.exists():
                try:
                    temporary_path.unlink()
                except OSError:
                    pass

    def _replace_with_retry(self, temporary_path: Path) -> None:
        """Retry transient Windows access-denied errors during replacement."""

        for attempt in range(1, self.replace_attempts + 1):
            try:
                os.replace(temporary_path, self.path)
                return
            except OSError as error:
                is_windows_lock = (
                    isinstance(error, PermissionError)
                    or getattr(error, "winerror", None) == 5
                )
                if not is_windows_lock or attempt >= self.replace_attempts:
                    raise

                delay = min(
                    self.initial_retry_delay_seconds * attempt,
                    self.max_retry_delay_seconds,
                )
                self.sleep_function(delay)


class AtomicJsonListStore(_AtomicJsonStore):
    """Read and atomically replace a JSON file containing a list."""

    def read(self) -> list[Any]:
        """Return the stored list, or an empty list when no file exists."""

        value = self._read_json([])
        if not isinstance(value, list):
            raise ValueError(f"{self.path} must contain a JSON list")
        return value

    def write(self, value: list[Any]) -> None:
        """Validate and atomically persist one JSON list."""

        if not isinstance(value, list):
            raise ValueError("AtomicJsonListStore requires a list")
        self._write_json(value)


class AtomicJsonDictStore(_AtomicJsonStore):
    """Read and atomically replace a JSON file containing an object."""

    def read(self) -> dict[str, Any]:
        """Return the stored mapping, or an empty dict when none exists."""

        value = self._read_json({})
        if not isinstance(value, Mapping):
            raise ValueError(f"{self.path} must contain a JSON object")
        return dict(value)

    def write(self, value: Mapping[str, Any]) -> None:
        """Validate and atomically persist one JSON mapping."""

        if not isinstance(value, Mapping):
            raise ValueError("AtomicJsonDictStore requires a mapping")
        self._write_json(dict(value))
