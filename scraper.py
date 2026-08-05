import html
import json
import logging
import os
import re
import time
import unicodedata
from typing import Any, Mapping

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

from alert_queue import PendingAlert, PendingAlertQueue
from html_adapters import (
    scrape_eightfold,
    scrape_successfactors,
    scrape_universal_playwright,
)
from location_filter import LocationFilter
from main import analyze_job

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

# טעינת משתני הסביבה
load_dotenv()

HISTORY_FILE = "jobs_history.json"
PENDING_ALERTS_FILE = "pending_alerts.json"
HTTP_TIMEOUT_SECONDS = 15

# חדש: רשימה שחורה - משרות שנדחה מיד גם אם יש בהן מילות סטודנט
EXCLUDE_KEYWORDS = [
    "senior", "lead", "manager", "director", "principal", "head", "vp", "expert", "architect"
]

STRONG_ENTRY_LEVEL_KEYWORDS = [
    "student", "student position", "student role", "working student",
    "student developer", "student software engineer", "student engineer",
    "intern", "internship", "university intern", "research intern",
    "summer intern", "co-op", "coop", "apprentice", "apprenticeship"
]

WEAK_ENTRY_LEVEL_KEYWORDS = [
    "part time", "part-time", "parttime", "junior", "entry level",
    "entry-level", "new grad", "new graduate", "new college grad",
    "college graduate", "recent graduate", "graduate position",
    "graduate program", "early career", "early careers",
    "early in profession", "trainee"
]

TARGET_ROLE_KEYWORDS = [
    "software engineer", "software developer", "software development",
    "backend", "back end", "back-end", "full stack", "full-stack",
    "developer", "development engineer", "r&d engineer",
    "algorithm", "algorithms", "algorithm engineer", "machine learning",
    "ml engineer", "ai engineer", "applied scientist", "research engineer",
    "computer vision", "deep learning", "nlp",
    "data scientist", "data science", "data analyst", "product analyst",
    "business data analyst", "data engineer", "analytics engineer", "data operations",
    "qa engineer", "software qa", "quality assurance", "automation engineer",
    "qa automation", "test automation", "software tester", "software testing",
    "verification engineer", "validation engineer", "v&v engineer",
    "devops", "cloud engineer", "platform engineer", "infrastructure engineer",
    "site reliability", "sre",
    "associate product manager", "product manager intern",
    "student product manager", "technical product manager", "product operations"
]

HEBREW_ENTRY_LEVEL_KEYWORDS = [
    "סטודנט", "סטודנטית", "משרת סטודנט", "משרת סטודנטית", "משרה לסטודנט",
    "משרה לסטודנטית", "התמחות", "מתמחה", "משרה חלקית", "חצי משרה",
    "בוגר", "בוגרת", "ללא ניסיון"
]

HEBREW_ROLE_KEYWORDS = [
    "פיתוח תוכנה", "מהנדס תוכנה", "מהנדסת תוכנה", "מפתח תוכנה", "מפתחת תוכנה",
    "אלגוריתמים", "למידת מכונה", "מדען נתונים", "מדענית נתונים",
    "אנליסט נתונים", "אנליסטית נתונים", "בדיקות תוכנה", "אוטומציה",
    "אבטחת מידע", "סייבר", "ניהול מוצר", "מנהל מוצר", "מנהלת מוצר"
]

def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text).lower()
    text = re.sub(r"[-_/]+", " ", text)
    text = re.sub(r"[^\w\u0590-\u05FF\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()

def contains_phrase(text: str, phrase: str) -> bool:
    normalized_text = normalize_text(text)
    normalized_phrase = normalize_text(phrase)
    pattern = rf"(?<!\w){re.escape(normalized_phrase)}(?!\w)"
    return re.search(pattern, normalized_text) is not None

def is_relevant_job(title):
    # 1. סינון ראשוני: העפת משרות מהרשימה השחורה
    if any(contains_phrase(title, kw) for kw in EXCLUDE_KEYWORDS):
        return False

    # 2. חיפוש מילות סטודנט חזקות
    if any(contains_phrase(title, kw) for kw in STRONG_ENTRY_LEVEL_KEYWORDS + HEBREW_ENTRY_LEVEL_KEYWORDS):
        return True
        
    # 3. שילוב של מילת כניסה חלשה + התאמה מקצועית
    has_weak_entry = any(contains_phrase(title, kw) for kw in WEAK_ENTRY_LEVEL_KEYWORDS)
    has_target_role = any(contains_phrase(title, kw) for kw in TARGET_ROLE_KEYWORDS + HEBREW_ROLE_KEYWORDS)
    
    if has_weak_entry and has_target_role:
        return True
        
    return False

def load_json(filepath):
    if not os.path.exists(filepath):
        return []
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)

def is_in_location(job_location, location_filters):
    if not location_filters or not job_location:
        return True
    job_loc_lower = job_location.lower()
    return any(loc.lower() in job_loc_lower for loc in location_filters)


def normalize_job_content(*values: Any) -> str:
    """Flatten available ATS fields into clean, factual job content."""

    content_parts: list[str] = []

    def collect(value: Any) -> None:
        if isinstance(value, str):
            text = BeautifulSoup(value, "lxml").get_text(" ", strip=True)
            if text and text not in content_parts:
                content_parts.append(text)
        elif isinstance(value, Mapping):
            for nested_value in value.values():
                collect(nested_value)
        elif isinstance(value, (list, tuple)):
            for nested_value in value:
                collect(nested_value)

    for value in values:
        collect(value)
    return "\n".join(content_parts)


def fetch_jobs_from_company(company):
    ats_type = company.get("ats_type")
    api_url = company.get("api_url")
    company_id = company.get("company_id")
    
    print(f"🔍 Scanning {company.get('company_name')} (ATS: {ats_type})...")
    
    # 1. Greenhouse (Regular & EU)
    if ats_type in ["greenhouse", "greenhouse_eu"]:
        try:
            response = requests.get(
                api_url,
                timeout=HTTP_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            data = response.json()
            jobs = []
            
            for job in data.get("jobs", []):
                jobs.append({
                    "id": f"{company_id}_{job.get('id')}",
                    "title": job.get("title", ""),
                    "location": job.get("location", {}).get("name", ""),
                    "url": job.get("absolute_url", ""),
                    "content": normalize_job_content(
                        job.get("content"),
                        job.get("description"),
                    ),
                })
            return jobs
        except Exception as e:
            print(f"❌ Error scanning Greenhouse {company_id}: {e}")
            return []
            
    # 2. Workday
    elif ats_type == "workday":
        try:
            headers = {"Accept": "application/json", "Content-Type": "application/json"}
            payload = {"limit": 20, "offset": 0, "appliedFacets": {}}
            
            response = requests.post(
                api_url,
                json=payload,
                headers=headers,
                timeout=HTTP_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            data = response.json()
            jobs = []
            
            base_url = api_url.split("/wday/cxs")[0]
            
            for job in data.get("jobPostings", []):
                job_url = f"{base_url}{job.get('externalPath', '')}"
                jobs.append({
                    "id": f"{company_id}_{job.get('bulletinId', job.get('id', ''))}",
                    "title": job.get("title", ""),
                    "location": job.get("locationsText", ""),
                    "url": job_url,
                    "content": normalize_job_content(
                        job.get("jobDescription"),
                        job.get("description"),
                    ),
                })
            return jobs
        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code
            if status_code in [401, 403, 422]:
                print(f"⚠️ {company_id} API returned {status_code} (Requires specific payload or auth).")
            else:
                print(f"❌ Network error on {company_id}: {status_code}")
            return []
        except Exception as e:
            print(f"❌ Error scanning Workday {company_id}: {e}")
            return []

    # 3. Amazon Jobs (JSON API)
    elif ats_type == "amazon_jobs":
        try:
            response = requests.get(
                api_url,
                timeout=HTTP_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            data = response.json()
            jobs = []
            
            for job in data.get("jobs", []):
                job_url = (
                    f"https://www.amazon.jobs"
                    f"{job.get('job_path', '')}"
                )
                jobs.append({
                    "id": f"{company_id}_{job.get('id_ic', job.get('id', ''))}",
                    "title": job.get("title", ""),
                    "location": job.get("city", ""),
                    "url": job_url,
                    "content": normalize_job_content(
                        job.get("description"),
                        job.get("basic_qualifications"),
                        job.get("preferred_qualifications"),
                    ),
                })
            return jobs
        except Exception as e:
            print(f"❌ Error scanning Amazon {company_id}: {e}")
            return []

    # 4. SmartRecruiters
    elif ats_type == "smartrecruiters":
        try:
            response = requests.get(
                api_url,
                timeout=HTTP_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            data = response.json()
            jobs = []
            
            for job in data.get("content", []):
                jobs.append({
                    "id": f"{company_id}_{job.get('id', '')}",
                    "title": job.get("name", ""),
                    "location": job.get("location", {}).get("city", ""),
                    "url": job.get("ref", ""),
                    "content": normalize_job_content(
                        job.get("jobAd"),
                        job.get("description"),
                    ),
                })
            return jobs
        except Exception as e:
            print(f"❌ Error scanning SmartRecruiters {company_id}: {e}")
            return []

    # 5. Ashby
    elif ats_type == "ashby":
        try:
            response = requests.get(
                api_url,
                timeout=HTTP_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            data = response.json()
            jobs = []
            
            for job in data.get("jobs", []):
                jobs.append({
                    "id": f"{company_id}_{job.get('id', '')}",
                    "title": job.get("title", ""),
                    "location": job.get("location", ""),
                    "url": job.get("jobUrl", ""),
                    "content": normalize_job_content(
                        job.get("descriptionPlain"),
                        job.get("descriptionHtml"),
                        job.get("description"),
                    ),
                })
            return jobs
        except Exception as e:
            print(f"❌ Error scanning Ashby {company_id}: {e}")
            return []

    # 6. SuccessFactors (HTML)
    elif ats_type == "successfactors":
        return scrape_successfactors(company)

    # 7. Eightfold API with Universal Playwright fallback
    elif ats_type == "eightfold":
        return scrape_eightfold(str(company_id), str(api_url))

    # 8. כל שאר חברות הביג-טק והמערכות הסגורות (Universal Playwright)
    elif ats_type in [
        "apple_custom",
        "microsoft_custom",
        "google_custom",
        "meta_custom",
        "ibm_custom",
        "oracle_recruiting_cloud",
        "phenom",
        "custom",
        "greenhouse_embedded",
        "comeet",
        "jobvite",
    ]:
        return scrape_universal_playwright(company)

    # 9. אם מסיבה כלשהי משהו נפל בין הכיסאות
    else:
        logging.warning(
            "No adapter available; skipping company_id=%s ats_type=%s",
            company_id,
            ats_type,
        )
        return []

def extract_job_url(job: Mapping[str, Any]) -> str:
    """Extract the best available job URL from an adapter result."""

    for key in ("url", "job_url", "absolute_url"):
        value = job.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    description = job.get("description", "")
    if not isinstance(description, str):
        return ""
    match = re.search(r'https?://[^\s<>"]+', description)
    if match is None:
        return ""
    return match.group(0).rstrip(".,);]")


def run_scraper(
    queue: PendingAlertQueue | None = None,
    location_filter: LocationFilter | None = None,
) -> None:
    """Scan, analyze, and enqueue new jobs without contacting Telegram."""

    print("🚀 מתחיל סריקת משרות...")
    total_start_time = time.time()  # תחילת המדידה הכוללת
    alert_queue = queue or PendingAlertQueue(PENDING_ALERTS_FILE)
    active_location_filter = (
        location_filter
        or LocationFilter(strict_mode=False)
    )
    
    companies = load_json("companies.json")
    if not companies:
        print("⚠️ קובץ companies.json ריק.")
        return

    history = set(load_json(HISTORY_FILE))
    pending_ids = alert_queue.ids()
    new_jobs_found = []
    queued_job_ids = set()

    # --- שלב 1: סריקת החברות ---
    for company in companies:
        if not company.get("is_active", True):
            continue
            
        jobs = fetch_jobs_from_company(company)
        location_filters = company.get("location_filters", [])
        
        for job in jobs:
            title_match = is_relevant_job(job["title"])
            job_url = (
                extract_job_url(job)
                or str(company.get("api_url", ""))
            )
            if title_match:
                location_decision = active_location_filter.evaluate(
                    job_title=job["title"],
                    job_url=job_url,
                )
                if not location_decision.allowed:
                    match_details = ""
                    if location_decision.matched_location is not None:
                        match_details = (
                            f" '{location_decision.matched_location}'"
                            f" in {location_decision.source}"
                        )
                    print(
                        f"🚫 Rejecting {job['id']}: "
                        f"{location_decision.reason}{match_details}."
                    )
                    continue

            location_match = is_in_location(job["location"], location_filters)
            is_new = (
                job["id"] not in history
                and job["id"] not in pending_ids
                and job["id"] not in queued_job_ids
            )
            
            if title_match and location_match and is_new:
                new_jobs_found.append({
                    **job,
                    "company_name": company.get(
                        "company_name",
                        company.get("company_id", "Unknown"),
                    ),
                    "job_url": job_url,
                })
                queued_job_ids.add(job["id"])

    scraping_end_time = time.time()  # סיום שלב הסריקה

    # --- שלב 2: ניתוח והוספה לתור ---
    if not new_jobs_found:
        print("\n😴 לא נמצאו משרות חדשות רלוונטיות הפעם.")
    else:
        print(f"\n✅ נמצאו {len(new_jobs_found)} משרות חדשות רלוונטיות. מעביר לסטיב...\n")
        
        for job in new_jobs_found:
            print(
                f"🤖 מנתח את: {job['title']} "
                f"במיקום {job['location']}"
            )

            try:
                analysis = analyze_job(
                    job_title=job["title"],
                    job_location=job["location"],
                    job_content=job.get("content", ""),
                )
            except Exception as error:
                print(
                    "❌ ניתוח המשרה נכשל; המשרה לא תיכנס לתור: "
                    f"{type(error).__name__}"
                )
                continue

            telegram_alert = (
                "🚨 <b>משרה חדשה נמצאה: "
                f"{html.escape(str(job['title']), quote=False)}</b> 🚨\n"
                "🏢 חברה: "
                f"{html.escape(str(job['company_name']), quote=False)}\n"
                "📍 מיקום: "
                f"{html.escape(str(job['location']), quote=False)}\n"
                "🔗 קישור: "
                f"{html.escape(str(job['job_url']), quote=False)}\n\n"
                f"{analysis}"
            )
            alert = PendingAlert(
                job_id=job["id"],
                company_name=job["company_name"],
                job_url=job["job_url"],
                llm_summary=telegram_alert,
            )
            if alert_queue.append(alert):
                pending_ids.add(job["id"])
                print(f"✅ המשרה {job['id']} נשמרה בתור ההתראות.")
            else:
                print(f"ℹ️ המשרה {job['id']} כבר קיימת בתור.")
            print("-" * 40)
    
    analysis_end_time = time.time()  # סיום שלב הניתוח
    
    # --- סיכום זמנים ---
    scraping_duration = scraping_end_time - total_start_time
    analysis_duration = analysis_end_time - scraping_end_time
    total_duration = analysis_end_time - total_start_time
    
    print("\n🏁 הסריקה הושלמה.")
    print("⏱️ דו\"ח ביצועים:")
    print(f"   - זמן סריקת אתרים: {scraping_duration:.1f} שניות")
    print(f"   - זמן ניתוח (AI) ושמירה לתור: {analysis_duration:.1f} שניות")
    print(f"   - סך הכל זמן ריצה: {total_duration:.1f} שניות")

if __name__ == "__main__":
    run_scraper()
