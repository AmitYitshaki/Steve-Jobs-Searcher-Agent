import requests
from typing import Any

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from playwright_scraper import PlaywrightJobScraper, ScrapeStatus

def scrape_successfactors(company):
    """
    סורק מערכות מבוססות SuccessFactors (כמו SAP, Elbit, Amdocs)
    """
    url = company.get("api_url")
    company_id = company.get("company_id")
    jobs = []
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        # הופך את טקסט האתר לאובייקט שאפשר לחפש בו
        soup = BeautifulSoup(response.text, 'lxml')
        
        # ב-SuccessFactors המשרות בדרך כלל יושבות בתוך טבלה, בשורות עם המחלקה 'data-row'
        job_rows = soup.find_all('tr', class_='data-row')
        
        # חילוץ כתובת הבסיס כדי לבנות לינקים תקינים (למשל https://jobs.sap.com)
        base_url = "/".join(url.split("/")[:3])
        
        for row in job_rows:
            # מציאת הכותרת והלינק
            title_tag = row.find('span', class_='jobTitle').find('a')
            if not title_tag:
                continue
                
            title = title_tag.text.strip()
            job_link = title_tag['href']
            
            if not job_link.startswith("http"):
                job_link = base_url + job_link
                
            # מציאת המיקום
            location_tag = row.find('span', class_='jobLocation')
            location = location_tag.text.strip() if location_tag else "Israel"

            description_tag = row.select_one(
                ".jobDescription, .job-description, .description"
            )
            content = (
                description_tag.get_text(" ", strip=True)
                if description_tag
                else ""
            )
            
            # יצירת מזהה ייחודי (בדרך כלל נמצא בלינק)
            job_id = job_link.split("/")[-2] if "/" in job_link else title
            
            jobs.append({
                "id": f"{company_id}_{job_id}",
                "title": title,
                "location": location,
                "url": job_link,
                "content": content,
            })
            
        return jobs
        
    except Exception as e:
        print(f"❌ Error scraping HTML for {company_id}: {e}")
        return []

def scrape_microsoft(company):
    """
    סורק אתר המשרות של מיקרוסופט באמצעות Playwright
    """
    url = company.get("api_url")
    company_id = company.get("company_id")
    jobs = []
    
    print(f"🕵️ מפעיל סורק עומק (Playwright) עבור {company_id}...")

    try:
        with sync_playwright() as p:
            # headless=True אומר שהדפדפן ירוץ ברקע בלי להפריע לך במסך
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url)
            
            # המתנה שהמשרות ייטענו
            page.wait_for_timeout(8000)
            html_content = page.content()
            browser.close()

        soup = BeautifulSoup(html_content, 'lxml')
        
        # אסטרטגיה למיקרוסופט: כל משרה היא לינק שמכיל /job/ בכתובת שלו
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            title = a_tag.text.strip()
            
            if '/job/' in href.lower() and len(title) > 3:
                # הרכבת הלינק המלא במידה וזה לינק יחסי
                full_link = href if href.startswith("http") else f"https://jobs.careers.microsoft.com{href}"
                job_id = href.split('/')[-1] if '/' in href else title
                
                jobs.append({
                    "id": f"{company_id}_{job_id}",
                    "title": title,
                    "location": "Israel", # מיקרוסופט מסננת לפי ישראל ב-URL במילא
                    "url": full_link,
                    "content": "",
                })
                
        return jobs
        
    except Exception as e:
        print(f"❌ שגיאה בסריקת מיקרוסופט: {e}")
        return []

def scrape_universal_playwright(
    company: dict[str, Any],
) -> list[dict[str, str]]:
    """Run the OOP Playwright scraper while preserving the legacy API."""

    company_id = str(company.get("company_id", "unknown"))
    print(f"🕵️ מפעיל סורק אוניברסלי (Playwright) עבור {company_id}...")

    result = PlaywrightJobScraper().scrape(company)
    if result.status is ScrapeStatus.WAF_BLOCKED:
        print(
            f"🛡️ {company_id} נחסם על ידי אתגר WAF: {result.message}. "
            "בדוק את debug_logs/api_discovery_log.json."
        )
    elif result.status is ScrapeStatus.NO_JOBS:
        print(f"⚠️ {company_id} החזיר 0 משרות: {result.message}")
    elif result.status is ScrapeStatus.FAILED:
        print(f"❌ שגיאה בסריקה אוניברסלית של {company_id}: {result.message}")

    return result.jobs
