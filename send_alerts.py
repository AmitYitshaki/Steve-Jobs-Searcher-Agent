"""Deliver queued job alerts when Telegram connectivity is available."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

from dotenv import load_dotenv

from storage.history import JobHistoryStore
from storage.queue import PendingAlertQueue
from telegram_notifier import NotificationResult, TelegramNotifier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)


class AlertSender(Protocol):
    """Define the notifier behavior required by the consumer."""

    def send(self, message: str) -> NotificationResult:
        """Send one formatted alert and return its terminal result."""


@dataclass(frozen=True)
class DeliverySummary:
    """Count the outcomes from one queue-processing run."""

    sent: int = 0
    failed: int = 0
    skipped: int = 0


class AlertConsumer:
    """Send pending alerts and commit successful deliveries to history."""

    def __init__(
        self,
        queue: PendingAlertQueue,
        history: JobHistoryStore,
        notifier: AlertSender,
    ) -> None:
        """Inject durable stores and a Telegram-compatible notifier."""

        self.queue = queue
        self.history = history
        self.notifier = notifier

    def run(self) -> DeliverySummary:
        """Process a queue snapshot while preserving every failed alert."""

        sent = 0
        failed = 0
        skipped = 0

        for alert in self.queue.load():
            if self.history.contains(alert.job_id):
                self.queue.remove(alert.job_id)
                skipped += 1
                print(
                    f"ℹ️ {alert.job_id} כבר בהיסטוריה והוסר מהתור."
                )
                continue

            try:
                result = self.notifier.send(alert.llm_summary)
            except Exception as error:
                failed += 1
                print(
                    f"❌ שליחת {alert.job_id} נכשלה "
                    f"({type(error).__name__}); ההתראה נשארה בתור."
                )
                continue

            if not result.success:
                failed += 1
                print(
                    f"❌ שליחת {alert.job_id} נכשלה "
                    f"({result.status.value}, {result.attempts} ניסיונות); "
                    "ההתראה נשארה בתור."
                )
                continue

            # History is committed first. If queue removal is interrupted,
            # the next run recognizes the delivery and removes it safely.
            self.history.add(alert.job_id)
            self.queue.remove(alert.job_id)
            sent += 1
            print(
                f"✅ ההתראה עבור {alert.company_name} "
                f"({alert.job_id}) נשלחה ונשמרה בהיסטוריה."
            )

        return DeliverySummary(
            sent=sent,
            failed=failed,
            skipped=skipped,
        )


def main() -> int:
    """Build the production consumer, process alerts, and return an exit code."""

    load_dotenv()
    try:
        with TelegramNotifier.from_environment() as notifier:
            summary = AlertConsumer(
                queue=PendingAlertQueue(),
                history=JobHistoryStore(),
                notifier=notifier,
            ).run()
    except (OSError, ValueError) as error:
        print(f"❌ לא ניתן לעבד את תור ההתראות: {error}")
        return 1

    print(
        "🏁 עיבוד התור הסתיים: "
        f"{summary.sent} נשלחו, "
        f"{summary.failed} נכשלו, "
        f"{summary.skipped} דולגו."
    )
    return 1 if summary.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
