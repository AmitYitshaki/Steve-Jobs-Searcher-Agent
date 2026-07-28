import os
import json
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI

# טעינת מפתח ה-API מקובץ .env
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

COSTS_FILE = "costs_log.json"

def log_cost(prompt_tokens, completion_tokens):
    """מחשב את עלות הקריאה ורושם אותה לקובץ לוג"""
    # תעריפי gpt-4o-mini (בדולרים למיליון טוקנים)
    input_price_per_1m = 0.15
    output_price_per_1m = 0.60

    # חישוב עלות
    cost = (prompt_tokens / 1_000_000) * input_price_per_1m + (completion_tokens / 1_000_000) * output_price_per_1m

    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "cost_usd": round(cost, 6)
    }

    # קריאת היסטוריית העלויות (אם קיימת)
    logs = []
    if os.path.exists(COSTS_FILE):
        try:
            with open(COSTS_FILE, "r", encoding="utf-8") as f:
                logs = json.load(f)
        except Exception:
            pass

    # הוספת הרשומה החדשה ושמירה
    logs.append(log_entry)
    with open(COSTS_FILE, "w", encoding="utf-8") as f:
        json.dump(logs, f, indent=4)

    return cost

def load_file(filename):
    """פונקציית עזר שטוענת קובץ טקסט/מרקדאון"""
    with open(filename, "r", encoding="utf-8") as f:
        return f.read()

def analyze_job(job_description):
    # 1. טעינת קבצי ההקשר של סטיב
    soul = load_file("agent_soul.md")
    identity = load_file("agent_identity.md")
    user_profile = load_file("user_profile.md")

    # 2. הרכבת ה-System Prompt המלא
    system_prompt = f"""
    {identity}
    
    {soul}
    
    --- USER CONTEXT ---
    {user_profile}
    """

    # 3. הנחיות הניתוח למשרה הספציפית
    user_prompt = f"""
    Analyze the following job description:
    
    {job_description}
    
    Provide a concise summary in Hebrew with the following structure:
    1. **תפקיד וחברה**: שם התפקיד והחברה.
    2. **דרישות סף טכניות**: מה הדיל-ברייקרים.
    3. **אחוז התאמה לפרופיל**: הערכת התאמה באחוזים מול המשתמש.
    4. **נקודות חוזק להדגשה בקורות החיים**: אילו פרויקטים/ניסיון מהפרופיל כדאי להבליט.
    """

    # 4. קריאה ל-API
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.2
    )

    # 5. מעקב טוקנים ושמירה ללוג
    prompt_tokens = response.usage.prompt_tokens
    completion_tokens = response.usage.completion_tokens
    cost = log_cost(prompt_tokens, completion_tokens)
    
    # הדפסה נחמדה שתופיע ליד הלוגים של טלגרם
    print(f"💰 [מעקב עלויות] צריכה: {prompt_tokens + completion_tokens} טוקנים | עלות: ${cost:.6f}")

    return response.choices[0].message.content

if __name__ == "__main__":
    # משרת בדיקה לדוגמה
    sample_job = """
    Company: SAP Israel (Raanana)
    Role: Student Developer - Backend
    Requirements:
    - B.Sc. student in Computer Science with at least 3 semesters remaining.
    - Strong knowledge in Object-Oriented Programming (C++ or Java or C#).
    - Experience with Data Structures and Algorithms.
    - Good communication skills, military leadership is an advantage.
    - Willingness to work 20 hours per week.
    """
    
    print("🤖 סטיב מנתח את המשרה...\n")
    result = analyze_job(sample_job)
    print("\n" + result)