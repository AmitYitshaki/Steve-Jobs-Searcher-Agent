import json
import os
import requests
import time
import re
import unicodedata
from dotenv import load_dotenv
from main import analyze_job
from html_adapters import scrape_successfactors, scrape_microsoft, scrape_universal_playwright

# טעינת משתני הסביבה
load_dotenv()

HISTORY_FILE = "jobs_history.json"

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

def save_json(filepath, data):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

def is_in_location(job_location, location_filters):
    if not location_filters or not job_location:
        return True
    job_loc_lower = job_location.lower()
    return any(loc.lower() in job_loc_lower for loc in location_filters)

def fetch_jobs_from_company(company):
    ats_type = company.get("ats_type")
    api_url = company.get("api_url")
    company_id = company.get("company_id")
    
    print(f"🔍 Scanning {company.get('company_name')} (ATS: {ats_type})...")
    
    # 1. Greenhouse (Regular & EU)
    if ats_type in ["greenhouse", "greenhouse_eu"]:
        try:
            response = requests.get(api_url)
            response.raise_for_status()
            data = response.json()
            jobs = []
            
            for job in data.get("jobs", []):
                jobs.append({
                    "id": f"{company_id}_{job.get('id')}",
                    "title": job.get("title", ""),
                    "location": job.get("location", {}).get("name", ""),
                    "description": f"Full job description available at: {job.get('absolute_url', '')}"
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
            
            response = requests.post(api_url, json=payload, headers=headers)
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
                    "description": f"Full job description available at: {job_url}"
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
            response = requests.get(api_url)
            response.raise_for_status()
            data = response.json()
            jobs = []
            
            for job in data.get("jobs", []):
                jobs.append({
                    "id": f"{company_id}_{job.get('id_ic', job.get('id', ''))}",
                    "title": job.get("title", ""),
                    "location": job.get("city", ""),
                    "description": f"Full job description available at: https://www.amazon.jobs{job.get('job_path', '')}"
                })
            return jobs
        except Exception as e:
            print(f"❌ Error scanning Amazon {company_id}: {e}")
            return []

    # 4. SmartRecruiters
    elif ats_type == "smartrecruiters":
        try:
            response = requests.get(api_url)
            response.raise_for_status()
            data = response.json()
            jobs = []
            
            for job in data.get("content", []):
                jobs.append({
                    "id": f"{company_id}_{job.get('id', '')}",
                    "title": job.get("name", ""),
                    "location": job.get("location", {}).get("city", ""),
                    "description": f"Full job description available at: {job.get('ref', '')}"
                })
            return jobs
        except Exception as e:
            print(f"❌ Error scanning SmartRecruiters {company_id}: {e}")
            return []

    # 5. Ashby
    elif ats_type == "ashby":
        try:
            response = requests.get(api_url)
            response.raise_for_status()
            data = response.json()
            jobs = []
            
            for job in data.get("jobs", []):
                jobs.append({
                    "id": f"{company_id}_{job.get('id', '')}",
                    "title": job.get("title", ""),
                    "location": job.get("location", ""),
                    "description": f"Full job description available at: {job.get('jobUrl', '')}"
                })
            return jobs
        except Exception as e:
            print(f"❌ Error scanning Ashby {company_id}: {e}")
            return []

    # 6. SuccessFactors (HTML)
    elif ats_type == "successfactors":
        return scrape_successfactors(company)

    # 7. Microsoft Careers (Playwright)
    elif ats_type == "microsoft_custom":
        return scrape_microsoft(company)

    # 8. כל שאר חברות הביג-טק והמערכות הסגורות (Universal Playwright)
    elif ats_type in [
        "apple_custom", "google_custom", "meta_custom", "ibm_custom", 
        "oracle_recruiting_cloud", "phenom", "custom", 
        "greenhouse_embedded", "comeet", "jobvite", "eightfold"
    ]:
        return scrape_universal_playwright(company)

    # 9. אם מסיבה כלשהי משהו נפל בין הכיסאות
    else:
        print(f"🚧 Skipping {company_id} ({ats_type}) - No adapter available.")
        return []

def send_telegram_message(message, session=None):
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if not token or not chat_id:
        print("❌ [דיאגנוסטיקה] חסר טוקן או צ'אט ID.")
        return

    url = f"https://api.telegram.org/bot{token.strip()}/sendMessage"
    clean_message = message.replace("**", "*")
    
    payload = {
        "chat_id": chat_id.strip(),
        "text": clean_message,
        "parse_mode": "Markdown"
    }
    
    req_method = session.post if session else requests.post

    try:
        response = req_method(url, json=payload, timeout=10)
        
        if response.status_code == 400 and "parse_mode" in payload:
            payload.pop("parse_mode", None)
            response = req_method(url, json=payload, timeout=10)
            
        response.raise_for_status()
        print("✅ [דיאגנוסטיקה] ההודעה נשלחה בהצלחה לטלגרם!")
        
    except (requests.exceptions.ConnectionError, ConnectionResetError) as e:
        print(f"❌ [דיאגנוסטיקה] השרת ניתק את החיבור בכוח (10054). מדלג כדי לא לבזבז זמן.")
    except Exception as e:
        print(f"❌ [דיאגנוסטיקה] שגיאה בשליחה: {e}")

def run_scraper():
    print("🚀 מתחיל סריקת משרות...")
    total_start_time = time.time()  # תחילת המדידה הכוללת
    
    companies = load_json("companies.json")
    if not companies:
        print("⚠️ קובץ companies.json ריק.")
        return

    history = set(load_json(HISTORY_FILE))
    new_jobs_found = []

    # --- שלב 1: סריקת החברות ---
    for company in companies:
        if not company.get("is_active", True):
            continue
            
        jobs = fetch_jobs_from_company(company)
        location_filters = company.get("location_filters", [])
        
        for job in jobs:
            title_match = is_relevant_job(job["title"])
            location_match = is_in_location(job["location"], location_filters)
            is_new = job["id"] not in history
            
            if title_match and location_match and is_new:
                new_jobs_found.append(job)
                history.add(job["id"])

    scraping_end_time = time.time()  # סיום שלב הסריקה

    # --- שלב 2: ניתוח ושליחה ---
    if not new_jobs_found:
        print("\n😴 לא נמצאו משרות חדשות רלוונטיות הפעם.")
    else:
        print(f"\n✅ נמצאו {len(new_jobs_found)} משרות חדשות רלוונטיות. מעביר לסטיב...\n")
        
        with requests.Session() as session:
            for job in new_jobs_found:
                print(f"🤖 מנתח את: {job['title']} במיקום {job['location']}")
                
                analysis = analyze_job(job["description"])
                telegram_alert = f"🚨 *משרה חדשה נמצאה: {job['title']}* 🚨\n📍 מיקום: {job['location']}\n\n{analysis}"
                
                send_telegram_message(telegram_alert, session=session)
                print("-" * 40)
                time.sleep(3)
        
    save_json(HISTORY_FILE, list(history))
    
    analysis_end_time = time.time()  # סיום שלב הניתוח
    
    # --- סיכום זמנים ---
    scraping_duration = scraping_end_time - total_start_time
    analysis_duration = analysis_end_time - scraping_end_time
    total_duration = analysis_end_time - total_start_time
    
    print("\n🏁 הסריקה הושלמה.")
    print("⏱️ דו\"ח ביצועים:")
    print(f"   - זמן סריקת אתרים: {scraping_duration:.1f} שניות")
    print(f"   - זמן ניתוח (AI) וטלגרם: {analysis_duration:.1f} שניות")
    print(f"   - סך הכל זמן ריצה: {total_duration:.1f} שניות")

if __name__ == "__main__":
    run_scraper()