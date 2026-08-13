import os
import json
import logging
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI

from paths import DATA_DIR, PROMPTS_DIR

LOGGER = logging.getLogger(__name__)

# טעינת מפתח ה-API מקובץ .env
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

COSTS_FILE = DATA_DIR / "costs_log.json"

# Generic fallbacks used when a prompt/context file is absent on a fresh
# deployment (e.g. config/prompts/user_profile.md is gitignored as personal
# data and never reaches the production server). Analysis then degrades to a
# generic prompt instead of crashing, so jobs still get analyzed and queued.
DEFAULT_IDENTITY_PROMPT = (
    "You are Steve, an AI assistant that helps a software engineering "
    "student find relevant entry-level and student positions."
)
DEFAULT_SOUL_PROMPT = (
    "Be concise, factual, and encouraging. Never invent job requirements; "
    "evaluate fit honestly against the supplied evidence only."
)
DEFAULT_USER_PROFILE_PROMPT = (
    "You are an AI assistant helping a software engineering student find "
    "relevant entry-level/student jobs. Analyze the job description and "
    "evaluate its relevance."
)

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
    COSTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(COSTS_FILE, "w", encoding="utf-8") as f:
        json.dump(logs, f, indent=4)

    return cost

def load_file(filename, fallback: str = "", label: str = "Prompt") -> str:
    """Load a prompt/context file, degrading to a fallback when it is missing.

    Personal context (like ``user_profile.md``) is gitignored and may never
    reach a fresh server, so a missing file must not crash analysis.
    """

    try:
        with open(filename, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        LOGGER.warning(
            "%s file not found at %s; falling back to the default generic "
            "prompt.",
            label,
            filename,
        )
        return fallback

def build_job_analysis_prompt(
    job_title: str,
    job_location: str,
    job_content: str | None,
) -> str:
    """Build an evidence-bound prompt from real job fields."""

    title = job_title.strip() or "Unknown title"
    location = job_location.strip() or "Unknown location"
    content = (job_content or "").strip()

    if content:
        evidence = f"""
    VERIFIED JOB POSTING CONTENT:
    {content}

    Use only the verified fields above. Do not invent requirements,
    responsibilities, seniority, company details, or technologies.
        """
    else:
        evidence = """
    NO FULL JOB DESCRIPTION WAS AVAILABLE.

    Estimate the typical requirements for this job based solely on the title.
    Then evaluate the user's fit against those estimated requirements.
    Explicitly state in the output that this is an estimation because the full
    job description was missing. Never present estimated details as verified
    facts about this specific opening.
        """

    return f"""
    Analyze this job using only the supplied evidence:

    JOB TITLE: {title}
    JOB LOCATION: {location}
    {evidence}

    FORMATTING RULES:
    - Return Telegram-compatible HTML, never Markdown.
    - Use only these standard formatting tags: <b>, <i>, <u>, <s>,
      <code>, and <pre>.
    - Use <b>...</b> for section headings. Never use Markdown bold syntax.
    - NEVER use Markdown code blocks or triple-backtick fences. Output plain
      text with only the allowed HTML tags above.
    - Do not emit links, attributes, custom tags, or raw angle brackets.

    Provide a concise summary in Hebrew with the following structure:
    1. <b>תפקיד ומיקום</b>: התפקיד והמיקום שסופקו.
    2. <b>דרישות סף טכניות</b>: דרישות מהתוכן המאומת; אם אין תוכן,
       דרישות טיפוסיות משוערות לפי שם התפקיד בלבד, עם סימון שהן משוערות.
    3. <b>אחוז התאמה לפרופיל</b>: הערכה מול הדרישות המאומתות; אם אין
       תוכן, הערכה חכמה מול הדרישות הטיפוסיות תוך ציון מפורש של מגבלת
       המידע.
    4. <b>נקודות חוזק להדגשה בקורות החיים</b>: רק נקודות שנתמכות בתוכן
       ובפרופיל המשתמש.
    """


def analyze_job(
    job_title: str,
    job_location: str,
    job_content: str | None = None,
) -> str:
    """Analyze a job without treating a URL as its description."""

    # 1. טעינת קבצי ההקשר של סטיב (עם fallback אם קובץ חסר בשרת)
    soul = load_file(
        PROMPTS_DIR / "agent_soul.md",
        fallback=DEFAULT_SOUL_PROMPT,
        label="Agent soul",
    )
    identity = load_file(
        PROMPTS_DIR / "agent_identity.md",
        fallback=DEFAULT_IDENTITY_PROMPT,
        label="Agent identity",
    )
    user_profile = load_file(
        PROMPTS_DIR / "user_profile.md",
        fallback=DEFAULT_USER_PROFILE_PROMPT,
        label="User profile",
    )

    # 2. הרכבת ה-System Prompt המלא
    system_prompt = f"""
    {identity}
    
    {soul}
    
    --- USER CONTEXT ---
    {user_profile}
    """

    # 3. הנחיות הניתוח למשרה הספציפית
    user_prompt = build_job_analysis_prompt(
        job_title=job_title,
        job_location=job_location,
        job_content=job_content,
    )

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
    result = analyze_job(
        job_title="Student Developer - Backend",
        job_location="Raanana, Israel",
        job_content=sample_job,
    )
    print("\n" + result)
