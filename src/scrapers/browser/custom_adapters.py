import hashlib
import logging
import requests
from typing import Any, Mapping
from urllib.parse import quote, urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup
from models.results import ScrapeStatus
from scrapers.browser.playwright_driver import PlaywrightJobScraper

LOGGER = logging.getLogger(__name__)
HTTP_TIMEOUT_SECONDS = 15
THALES_PHENOM_PAGE_SIZE = 10
THALES_PHENOM_MAX_PAGES = 100
IAI_REQUEST_HEADERS = {
    "Accept": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/152.0.0.0 Safari/537.36"
    ),
}
THALES_REQUEST_HEADERS = {
    **IAI_REQUEST_HEADERS,
    "Accept": "application/json",
    "Content-Type": "application/json",
}


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


def scrape_iai(
    company: Mapping[str, Any],
) -> list[dict[str, str]]:
    """Normalize IAI's first-party JSON feed into shared job records."""

    company_id = str(company.get("company_id", "iai")).strip() or "iai"
    api_url = str(company.get("api_url", "")).strip()
    if not api_url:
        LOGGER.error("IAI adapter requires an api_url")
        return []

    try:
        response = requests.get(
            api_url,
            headers=IAI_REQUEST_HEADERS,
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError, TypeError) as error:
        LOGGER.error("IAI jobs API request failed: %s", error)
        return []

    if not isinstance(payload, list):
        LOGGER.error(
            "IAI jobs API returned %s instead of a list",
            type(payload).__name__,
        )
        return []

    parsed_api_url = urlsplit(api_url)
    origin = urlunsplit(
        (parsed_api_url.scheme, parsed_api_url.netloc, "/", "", "")
    )
    jobs: list[dict[str, str]] = []
    for item in payload:
        if not isinstance(item, Mapping):
            continue

        raw_job_id = item.get("id")
        title = str(item.get("tl", "")).strip()
        if raw_job_id is None or not title:
            continue
        job_id = str(raw_job_id).strip()
        if not job_id:
            continue

        encoded_job_id = quote(job_id, safe="")
        jobs.append(
            {
                "id": f"{company_id}_{job_id}",
                "title": title,
                "location": str(item.get("ct", "")).strip(),
                "url": urljoin(origin, f"job/{encoded_job_id}/"),
                "content": str(item.get("dc", "")).strip(),
            }
        )

    return jobs


def _thales_phenom_payload(offset: int) -> dict[str, Any]:
    """Build one Thales Phenom request scoped to the Israel country facet."""

    return {
        "lang": "en_global",
        "deviceType": "desktop",
        "country": "global",
        "pageName": "search-results",
        "ddoKey": "refineSearch",
        "sortBy": "",
        "subsearch": "",
        "from": offset,
        "jobs": True,
        "counts": True,
        "all_fields": [
            "category",
            "country",
            "state",
            "city",
            "type",
            "workerSubType",
            "workLocation",
        ],
        "size": THALES_PHENOM_PAGE_SIZE,
        "clearAll": False,
        "jdsource": "facets",
        "isSliderEnable": False,
        "pageId": "page18",
        "siteType": "external",
        "keywords": "",
        "global": True,
        "selected_fields": {"country": ["Israel"]},
        "locationData": {},
    }


def _thales_phenom_page(
    payload: Any,
) -> tuple[list[Mapping[str, Any]], int]:
    """Extract normalized page metadata from a Thales widgets response."""

    if not isinstance(payload, Mapping):
        return [], 0
    search_result = payload.get("refineSearch")
    if not isinstance(search_result, Mapping):
        return [], 0
    data = search_result.get("data")
    if not isinstance(data, Mapping):
        return [], 0
    raw_jobs = data.get("jobs")
    if not isinstance(raw_jobs, list):
        return [], 0

    jobs = [
        item
        for item in raw_jobs
        if isinstance(item, Mapping)
    ]
    raw_total = search_result.get("totalHits", len(jobs))
    try:
        total_hits = max(int(raw_total), 0)
    except (TypeError, ValueError):
        total_hits = len(jobs)
    return jobs, total_hits


def _join_distinct_text(*values: Any) -> str:
    """Join non-empty text values once while preserving source order."""

    parts: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        normalized = text.casefold()
        if not text or normalized in seen:
            continue
        seen.add(normalized)
        parts.append(text)
    return " | ".join(parts)


def scrape_thales_phenom(
    company: Mapping[str, Any],
) -> list[dict[str, str]]:
    """Fetch all Thales jobs selected by the Israel country facet."""

    company_id = (
        str(company.get("company_id", "imperva_thales")).strip()
        or "imperva_thales"
    )
    api_url = str(company.get("api_url", "")).strip()
    if not api_url:
        LOGGER.error("Thales Phenom adapter requires an api_url")
        return []

    jobs: list[dict[str, str]] = []
    seen_job_ids: set[str] = set()
    page_offset = 0

    for _page_number in range(THALES_PHENOM_MAX_PAGES):
        try:
            response = requests.post(
                api_url,
                json=_thales_phenom_payload(page_offset),
                headers=THALES_REQUEST_HEADERS,
                timeout=HTTP_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            items, total_hits = _thales_phenom_page(response.json())
        except (
            requests.RequestException,
            TypeError,
            ValueError,
        ) as error:
            LOGGER.error(
                "Thales Phenom API request failed at offset %s: %s",
                page_offset,
                error,
            )
            break

        if not items:
            break

        for item in items:
            country = str(item.get("country", "")).strip()
            if country.casefold() != "israel":
                LOGGER.warning(
                    "Skipping out-of-scope Thales job %r from %r",
                    item.get("jobId"),
                    country,
                )
                continue

            raw_job_id = item.get("jobId") or item.get("reqId")
            title = str(item.get("title", "")).strip()
            if raw_job_id is None or not title:
                continue
            job_id = str(raw_job_id).strip()
            if not job_id or job_id in seen_job_ids:
                continue

            job_url = str(item.get("applyUrl", "")).strip()
            if not job_url:
                job_url = (
                    "https://careers.thalesgroup.com/global/en/job/"
                    f"{quote(job_id, safe='')}"
                )

            seen_job_ids.add(job_id)
            jobs.append(
                {
                    "id": f"{company_id}_{job_id}",
                    "title": title,
                    "location": _join_distinct_text(
                        item.get("cityStateCountry"),
                        item.get("location"),
                        item.get("address"),
                        country,
                    ),
                    "url": job_url,
                    "content": str(
                        item.get("descriptionTeaser", "")
                    ).strip(),
                }
            )

        next_offset = page_offset + len(items)
        if next_offset <= page_offset:
            break
        if total_hits > 0 and next_offset >= total_hits:
            break
        if total_hits == 0 and len(items) < THALES_PHENOM_PAGE_SIZE:
            break
        page_offset = next_offset

    return jobs


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
            location = location_tag.text.strip() if location_tag else ""

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
            "בדוק את logs/api_discovery_log.json."
        )
    elif result.status is ScrapeStatus.NO_JOBS:
        print(f"⚠️ {company_id} החזיר 0 משרות: {result.message}")
    elif result.status is ScrapeStatus.FAILED:
        print(f"❌ שגיאה בסריקה אוניברסלית של {company_id}: {result.message}")

    return result.jobs
