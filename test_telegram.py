import os
import requests
from dotenv import load_dotenv

load_dotenv()

token = os.getenv("TELEGRAM_TOKEN")
chat_id = os.getenv("TELEGRAM_CHAT_ID")

url = f"https://api.telegram.org/bot{token.strip()}/sendMessage"
payload = {
    "chat_id": chat_id.strip(),
    "text": "🧪 *הודעת טסט מסטיב:* החיבור לטלגרם עובד בצורה תקינה!",
    "parse_mode": "Markdown"
}

with requests.Session() as session:
    try:
        response = session.post(url, json=payload, timeout=10)
        response.raise_for_status()
        print("✅ הצלחה! ההודעה הגיעה לטלגרם.")
    except Exception as e:
        print(f"❌ עדיין יש שגיאה בחיבור: {e}")