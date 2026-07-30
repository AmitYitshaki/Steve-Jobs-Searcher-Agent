"""Manual Telegram connectivity check; never imported as an automated test."""

import os

import requests
from dotenv import load_dotenv


def run_telegram_check() -> None:
    """Send one real Telegram message when run explicitly."""

    load_dotenv()
    token = os.getenv("TELEGRAM_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        raise ValueError("Telegram credentials are required")

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": "🧪 הודעת טסט מסטיב: החיבור לטלגרם עובד בצורה תקינה!",
    }

    with requests.Session() as session:
        try:
            response = session.post(url, json=payload, timeout=10)
            response.raise_for_status()
            print("✅ הצלחה! ההודעה הגיעה לטלגרם.")
        except requests.RequestException as error:
            print(f"❌ עדיין יש שגיאה בחיבור: {error}")


if __name__ == "__main__":
    run_telegram_check()
