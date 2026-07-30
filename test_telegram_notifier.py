"""Deterministic tests for resilient Telegram delivery."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

import requests
from requests import Response

from telegram_notifier import (
    NotificationStatus,
    RetryPolicy,
    TelegramNotifier,
)


def make_response(
    status_code: int,
    json_data: object | None = None,
    headers: dict[str, str] | None = None,
) -> MagicMock:
    """Create a minimal mocked requests response."""

    response = MagicMock(spec=Response)
    response.status_code = status_code
    response.headers = headers or {}
    response.json.return_value = json_data if json_data is not None else {}
    return response


class TelegramNotifierTests(unittest.TestCase):
    """Verify success, retry, rate-limit, and permanent-failure paths."""

    def setUp(self) -> None:
        """Create deterministic retry dependencies for each test."""

        self.session = MagicMock(spec=requests.Session)
        self.sleep = MagicMock()
        self.policy = RetryPolicy(
            max_attempts=3,
            base_delay_seconds=1.0,
            max_delay_seconds=8.0,
            jitter_ratio=0.0,
        )

    def build_notifier(self) -> TelegramNotifier:
        """Return a notifier using the test session and deterministic clock."""

        return TelegramNotifier(
            token="test-token",
            chat_id="test-chat",
            session=self.session,
            retry_policy=self.policy,
            sleep_function=self.sleep,
        )

    def test_sends_successfully_without_retry(self) -> None:
        """Return SENT immediately after a successful response."""

        self.session.post.return_value = make_response(200)

        result = self.build_notifier().send("hello")

        self.assertTrue(result.success)
        self.assertEqual(result.status, NotificationStatus.SENT)
        self.assertEqual(result.attempts, 1)
        self.sleep.assert_not_called()

    def test_retries_connection_reset_then_succeeds(self) -> None:
        """Retry Windows ConnectionResetError with exponential backoff."""

        self.session.post.side_effect = [
            ConnectionResetError(10054, "connection reset"),
            make_response(200),
        ]

        result = self.build_notifier().send("hello")

        self.assertTrue(result.success)
        self.assertEqual(result.attempts, 2)
        self.sleep.assert_called_once_with(1.0)

    def test_uses_exponential_backoff_for_server_errors(self) -> None:
        """Double the delay between retryable server failures."""

        self.session.post.side_effect = [
            make_response(500),
            make_response(502),
            make_response(200),
        ]

        result = self.build_notifier().send("hello")

        self.assertTrue(result.success)
        self.assertEqual(result.attempts, 3)
        self.assertEqual(
            [call.args[0] for call in self.sleep.call_args_list],
            [1.0, 2.0],
        )

    def test_returns_retry_exhausted_after_transient_failures(self) -> None:
        """Stop after the configured number of network attempts."""

        self.session.post.side_effect = [
            requests.exceptions.ConnectionError("offline"),
            requests.exceptions.ConnectionError("offline"),
            requests.exceptions.ConnectionError("offline"),
        ]

        result = self.build_notifier().send("hello")

        self.assertEqual(result.status, NotificationStatus.RETRY_EXHAUSTED)
        self.assertEqual(result.attempts, 3)
        self.assertEqual(
            [call.args[0] for call in self.sleep.call_args_list],
            [1.0, 2.0],
        )

    def test_honors_telegram_retry_after_on_rate_limit(self) -> None:
        """Wait at least Telegram's requested delay after HTTP 429."""

        self.session.post.side_effect = [
            make_response(
                429,
                json_data={"parameters": {"retry_after": 7}},
            ),
            make_response(200),
        ]

        result = self.build_notifier().send("hello")

        self.assertTrue(result.success)
        self.sleep.assert_called_once_with(7.0)

    def test_retries_html_parse_error_without_parse_mode(self) -> None:
        """Retry raw plain text if Telegram rejects HTML parsing."""

        self.session.post.side_effect = [
            make_response(400),
            make_response(200),
        ]

        result = self.build_notifier().send("**broken <markup>**")

        self.assertTrue(result.success)
        self.assertEqual(result.attempts, 2)
        self.sleep.assert_not_called()
        first_payload = self.session.post.call_args_list[0].kwargs["json"]
        self.assertEqual(first_payload["parse_mode"], "HTML")
        self.assertEqual(
            first_payload["text"],
            "**broken &lt;markup&gt;**",
        )
        second_payload = self.session.post.call_args_list[1].kwargs["json"]
        self.assertNotIn("parse_mode", second_payload)
        self.assertEqual(second_payload["text"], "**broken <markup>**")

    def test_escapes_untrusted_text_for_html_parse_mode(self) -> None:
        """Preserve approved formatting and escape unsupported markup."""

        self.session.post.return_value = make_response(200)

        self.build_notifier().send(
            "Junior_[R&D] *Intern* `role` "
            "<script>unsafe</script> <b>safe &amp; bold</b>"
        )

        payload = self.session.post.call_args.kwargs["json"]
        self.assertEqual(payload["parse_mode"], "HTML")
        self.assertEqual(
            payload["text"],
            "Junior_[R&amp;D] *Intern* `role` "
            "&lt;script&gt;unsafe&lt;/script&gt; "
            "<b>safe &amp; bold</b>",
        )

    def test_does_not_retry_permanent_client_error(self) -> None:
        """Fail immediately for authentication and other permanent errors."""

        self.session.post.return_value = make_response(401)

        result = self.build_notifier().send("hello")

        self.assertEqual(result.status, NotificationStatus.PERMANENT_FAILURE)
        self.assertEqual(result.attempts, 1)
        self.assertEqual(result.status_code, 401)
        self.sleep.assert_not_called()

    def test_environment_factory_requires_credentials(self) -> None:
        """Reject missing environment credentials before making a request."""

        with self.assertRaises(ValueError):
            TelegramNotifier.from_environment(environment={})

    def test_result_does_not_expose_bot_token(self) -> None:
        """Keep the secret bot token out of terminal-safe errors."""

        secret_token = "super-secret-token"
        self.session.post.side_effect = requests.exceptions.ConnectionError(
            f"https://api.telegram.org/bot{secret_token}/sendMessage"
        )
        notifier = TelegramNotifier(
            token=secret_token,
            chat_id="test-chat",
            session=self.session,
            retry_policy=RetryPolicy(
                max_attempts=1,
                jitter_ratio=0.0,
            ),
            sleep_function=self.sleep,
        )

        result = notifier.send("hello")

        self.assertNotIn(secret_token, result.error)
        self.assertEqual(result.error, "ConnectionError")


class RetryPolicyTests(unittest.TestCase):
    """Validate fail-fast retry configuration."""

    def test_rejects_invalid_attempt_count(self) -> None:
        """Require at least one delivery attempt."""

        with self.assertRaises(ValueError):
            RetryPolicy(max_attempts=0)

    def test_rejects_invalid_jitter_ratio(self) -> None:
        """Keep jitter within a bounded zero-to-one ratio."""

        with self.assertRaises(ValueError):
            RetryPolicy(jitter_ratio=1.5)


if __name__ == "__main__":
    unittest.main()
