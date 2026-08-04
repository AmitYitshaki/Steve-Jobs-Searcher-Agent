import hashlib
import logging
import requests
from typing import Any, Mapping
from urllib.parse import urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from playwright_scraper import PlaywrightJobScraper, ScrapeStatus

LOGGER = logging.getLogger(__name__)
HTTP_TIMEOUT_SECONDS = 15


def _eightfold_api_url(url: str) -> str:
    """Build the conventional Eightfold jobs endpoint on the same origin."""

    parsed_url = urlsplit(url)
    if not parsed_url.scheme or not parsed_url.netloc:
        raise ValueError("Eightfold URL must be absolute")
    return urlunsplit(
        (
            parsed_url.scheme,
            parsed_url.netloc,
            "/api/apply/v2/jobs",
            "",
            "",
        )
    )


def _eightfold_job_items(payload: Any) -> list[Mapping[str, Any]]:
    """Extract job objects from common Eightfold response envelopes."""

    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, Mapping)]
    if not isinstance(payload, Mapping):
        return []

    for key in ("positions", "jobs", "results"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, Mapping)]

    nested_data = payload.get("data")
    if isinstance(nested_data, (list, Mapping)):
        return _eightfold_job_items(nested_data)
    return []


def _flatten_eightfold_text(value: Any) -> str:
    """Convert nested Eightfold text fields into readable plain text."""

    if isinstance(value, str):
        return BeautifulSoup(value, "lxml").get_text(" ", strip=True)
    if isinstance(value, Mapping):
        parts = [
            _flatten_eightfold_text(nested_value)
            for nested_value in value.values()
        ]
    elif isinstance(value, list):
        parts = [_flatten_eightfold_text(item) for item in value]
    else:
        return ""
    return ", ".join(part for part in parts if part)


def scrape_eightfold(
    company_id: str,
    url: str,
) -> list[dict[str, str]]:
    """Use Eightfold's JSON endpoint with Universal Playwright fallback."""

    fallback_company = {
        "company_id": company_id,
        "api_url": url,
    }
    try:
        api_url = _eightfold_api_url(url)
        response = requests.get(
            api_url,
            headers={
                "Accept": "application/json",
                "User-Agent": "Mozilla/5.0",
            },
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        items = _eightfold_job_items(response.json())
        jobs: list[dict[str, str]] = []

        for item in items:
            title = _flatten_eightfold_text(
                item.get("title") or item.get("name")
            )
            if not title:
                continue

            location = _flatten_eightfold_text(
                item.get("location")
                or item.get("locations")
                or item.get("locationName")
            )
            raw_job_url = _flatten_eightfold_text(
                item.get("canonicalPositionUrl")
                or item.get("jobUrl")
                or item.get("applyUrl")
                or item.get("positionUrl")
                or item.get("url")
            )
            job_url = urljoin(url, raw_job_url) if raw_job_url else url
            content = _flatten_eightfold_text(
                item.get("description")
                or item.get("jobDescription")
                or item.get("content")
            )
            raw_job_id = (
                item.get("id")
                or item.get("positionId")
                or item.get("jobId")
                or item.get("requisitionId")
            )
            if raw_job_id is None:
                raw_job_id = hashlib.sha256(
                    f"{title}|{location}|{job_url}".encode("utf-8")
                ).hexdigest()[:16]

            jobs.append(
                {
                    "id": f"{company_id}_{raw_job_id}",
                    "title": title,
                    "location": location,
                    "url": job_url,
                    "content": content,
                }
            )

        if jobs:
            return jobs
        LOGGER.warning(
            "Eightfold API returned no usable jobs for %s; using "
            "Playwright fallback",
            company_id,
        )
    except (requests.RequestException, ValueError, TypeError) as error:
        LOGGER.warning(
            "Eightfold API unavailable for %s (%s); using Playwright "
            "fallback",
            company_id,
            error,
        )

    return scrape_universal_playwright(fallback_company)


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
