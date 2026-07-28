"""Reliable Telegram notification delivery with bounded retries."""

from __future__ import annotations

import os
import random
import time
from dataclasses import dataclass
from enum import Enum
from types import TracebackType
from typing import Callable, Mapping

import requests
from requests import Response

SleepFunction = Callable[[float], None]
RandomFunction = Callable[[], float]


class NotificationStatus(str, Enum):
    """Represent the terminal outcome of a Telegram send operation."""

    SENT = "sent"
    PERMANENT_FAILURE = "permanent_failure"
    RETRY_EXHAUSTED = "retry_exhausted"


@dataclass(frozen=True)
class NotificationResult:
    """Describe a Telegram send outcome without exposing credentials."""

    status: NotificationStatus
    attempts: int
    status_code: int | None = None
    error: str = ""

    @property
    def success(self) -> bool:
        """Return whether Telegram accepted the notification."""

        return self.status is NotificationStatus.SENT


@dataclass(frozen=True)
class RetryPolicy:
    """Configure bounded exponential backoff and optional jitter."""

    max_attempts: int = 3
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 30.0
    jitter_ratio: float = 0.2

    def __post_init__(self) -> None:
        """Validate retry settings at construction time."""

        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.base_delay_seconds < 0:
            raise ValueError("base_delay_seconds cannot be negative")
        if self.max_delay_seconds < self.base_delay_seconds:
            raise ValueError(
                "max_delay_seconds cannot be below base_delay_seconds"
            )
        if not 0 <= self.jitter_ratio <= 1:
            raise ValueError("jitter_ratio must be between 0 and 1")


class TelegramNotifier:
    """Send Telegram messages with safe, retry-aware error handling."""

    RETRYABLE_EXCEPTIONS = (
        requests.exceptions.ConnectionError,
        requests.exceptions.Timeout,
        requests.exceptions.ChunkedEncodingError,
        ConnectionResetError,
    )

    def __init__(
        self,
        token: str,
        chat_id: str,
        session: requests.Session | None = None,
        retry_policy: RetryPolicy | None = None,
        timeout_seconds: float = 10.0,
        sleep_function: SleepFunction = time.sleep,
        random_function: RandomFunction = random.random,
    ) -> None:
        """Initialize Telegram credentials, transport, and retry policy."""

        clean_token = token.strip()
        clean_chat_id = chat_id.strip()
        if not clean_token:
            raise ValueError("TELEGRAM_TOKEN is required")
        if not clean_chat_id:
            raise ValueError("TELEGRAM_CHAT_ID is required")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

        self._endpoint = (
            f"https://api.telegram.org/bot{clean_token}/sendMessage"
        )
        self.chat_id = clean_chat_id
        self.retry_policy = retry_policy or RetryPolicy()
        self.timeout_seconds = timeout_seconds
        self.sleep_function = sleep_function
        self.random_function = random_function
        self.session = session or requests.Session()
        self._owns_session = session is None

    @classmethod
    def from_environment(
        cls,
        session: requests.Session | None = None,
        retry_policy: RetryPolicy | None = None,
        timeout_seconds: float = 10.0,
        sleep_function: SleepFunction = time.sleep,
        random_function: RandomFunction = random.random,
        environment: Mapping[str, str] | None = None,
    ) -> TelegramNotifier:
        """Build a notifier from Telegram environment variables."""

        source = environment if environment is not None else os.environ
        return cls(
            token=source.get("TELEGRAM_TOKEN", ""),
            chat_id=source.get("TELEGRAM_CHAT_ID", ""),
            session=session,
            retry_policy=retry_policy,
            timeout_seconds=timeout_seconds,
            sleep_function=sleep_function,
            random_function=random_function,
        )

    def __enter__(self) -> TelegramNotifier:
        """Return this notifier for context-manager usage."""

        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close an internally owned HTTP session."""

        self.close()

    def close(self) -> None:
        """Close the HTTP session only when this instance created it."""

        if self._owns_session:
            self.session.close()

    def send(self, message: str) -> NotificationResult:
        """Send one message, retrying transient failures with backoff."""

        payload: dict[str, str] = {
            "chat_id": self.chat_id,
            "text": message.replace("**", "*"),
            "parse_mode": "Markdown",
        }
        attempts = 0

        while attempts < self.retry_policy.max_attempts:
            attempts += 1
            try:
                response = self.session.post(
                    self._endpoint,
                    json=payload,
                    timeout=self.timeout_seconds,
                )
            except self.RETRYABLE_EXCEPTIONS as error:
                if attempts >= self.retry_policy.max_attempts:
                    return NotificationResult(
                        status=NotificationStatus.RETRY_EXHAUSTED,
                        attempts=attempts,
                        error=type(error).__name__,
                    )
                self.sleep_function(self._backoff_delay(attempts))
                continue
            except requests.exceptions.RequestException as error:
                return NotificationResult(
                    status=NotificationStatus.PERMANENT_FAILURE,
                    attempts=attempts,
                    error=type(error).__name__,
                )

            if 200 <= response.status_code < 300:
                return NotificationResult(
                    status=NotificationStatus.SENT,
                    attempts=attempts,
                    status_code=response.status_code,
                )

            if response.status_code == 400 and "parse_mode" in payload:
                payload.pop("parse_mode")
                if attempts < self.retry_policy.max_attempts:
                    continue

            if self._is_retryable_status(response.status_code):
                if attempts >= self.retry_policy.max_attempts:
                    return NotificationResult(
                        status=NotificationStatus.RETRY_EXHAUSTED,
                        attempts=attempts,
                        status_code=response.status_code,
                        error=f"Telegram HTTP {response.status_code}",
                    )
                delay = self._backoff_delay(attempts)
                retry_after = self._retry_after_seconds(response)
                if retry_after is not None:
                    delay = max(delay, retry_after)
                self.sleep_function(delay)
                continue

            return NotificationResult(
                status=NotificationStatus.PERMANENT_FAILURE,
                attempts=attempts,
                status_code=response.status_code,
                error=f"Telegram HTTP {response.status_code}",
            )

        return NotificationResult(
            status=NotificationStatus.RETRY_EXHAUSTED,
            attempts=attempts,
            error="Retry policy exhausted",
        )

    @staticmethod
    def _is_retryable_status(status_code: int) -> bool:
        """Return whether an HTTP status is transient."""

        return status_code == 429 or 500 <= status_code < 600

    def _backoff_delay(self, failed_attempt: int) -> float:
        """Calculate capped exponential backoff with symmetric jitter."""

        uncapped_delay = (
            self.retry_policy.base_delay_seconds
            * (2 ** (failed_attempt - 1))
        )
        capped_delay = min(
            uncapped_delay,
            self.retry_policy.max_delay_seconds,
        )
        jitter_span = capped_delay * self.retry_policy.jitter_ratio
        jitter = ((self.random_function() * 2) - 1) * jitter_span
        return max(0.0, capped_delay + jitter)

    @staticmethod
    def _retry_after_seconds(response: Response) -> float | None:
        """Extract Telegram's requested retry delay from JSON or headers."""

        try:
            response_data = response.json()
        except ValueError:
            response_data = {}

        if isinstance(response_data, dict):
            parameters = response_data.get("parameters")
            if isinstance(parameters, dict):
                retry_after = parameters.get("retry_after")
                try:
                    return max(0.0, float(retry_after))
                except (TypeError, ValueError):
                    pass

        header_value = response.headers.get("Retry-After")
        if header_value is None:
            return None
        try:
            return max(0.0, float(header_value))
        except ValueError:
            return None
