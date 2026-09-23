import hashlib
import html
import json
import logging
import re
import requests
from typing import Any, Mapping
from urllib.parse import quote, urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup
from models.results import ScrapeResult, ScrapeStatus
from scrapers.api.client import normalize_job_content
from scrapers.artifacts import extract_sample_titles, write_company_artifacts
from scrapers.browser.playwright_driver import (
    CompanyConfig,
    EmbeddedJsonScraper,
    NetworkInterceptScraper,
    PlaywrightJobScraper,
)

LOGGER = logging.getLogger(__name__)
HTTP_TIMEOUT_SECONDS = 15
THALES_PHENOM_PAGE_SIZE = 10
THALES_PHENOM_MAX_PAGES = 100
META_JOBS_URL = "https://www.metacareers.com/jobs?q=Israel"
GOOGLE_JOBS_BASE_URL = (
    "https://www.google.com/about/careers/applications/jobs/results"
)
GOOGLE_QUERY_VARIANTS = (
    "location=Israel&target_level=EARLY",
    "location=Israel&employment_type=INTERN",
)
GOOGLE_MAX_PAGES_PER_VARIANT = 10
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
# Comeet boards and embeds return HTML, not JSON; requesting
# Accept: application/json (IAI_REQUEST_HEADERS' default) gets a 406 from
# Comeet's edge.
COMEET_REQUEST_HEADERS = {
    **IAI_REQUEST_HEADERS,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
COMEET_BLOCKING_HTTP_STATUS_CODES = frozenset({401, 403, 429})


def _meta_text(value: Any) -> str:
    """Normalize one textual value from Meta's nested GraphQL objects."""

    if isinstance(value, str):
        return value.strip()
    if isinstance(value, Mapping):
        for key in ("name", "label", "text", "title"):
            text = value.get(key)
            if isinstance(text, str) and text.strip():
                return text.strip()
    return ""


def _meta_job_search_parser(payload: Any) -> list[dict[str, str]]:
    """Normalize Meta's job-search GraphQL payload into shared records."""

    if not isinstance(payload, Mapping):
        return []
    data = payload.get("data")
    if not isinstance(data, Mapping):
        return []
    search_result = data.get("job_search_with_featured_jobs_v2")
    if not isinstance(search_result, Mapping):
        return []
    all_jobs = search_result.get("all_jobs")
    if not isinstance(all_jobs, list):
        return []

    jobs: list[dict[str, str]] = []
    for item in all_jobs:
        if not isinstance(item, Mapping):
            continue
        raw_job_id = item.get("id")
        title = _meta_text(item.get("title"))
        if raw_job_id is None or not title:
            continue
        job_id = str(raw_job_id).strip()
        if not job_id:
            continue

        raw_locations = item.get("locations")
        if isinstance(raw_locations, list):
            locations = [_meta_text(value) for value in raw_locations]
        else:
            locations = [_meta_text(raw_locations)]
        location = ", ".join(value for value in locations if value)
        raw_teams = item.get("teams")
        if isinstance(raw_teams, list):
            teams = [_meta_text(team) for team in raw_teams]
        else:
            teams = [_meta_text(raw_teams)]
        content = ", ".join(team for team in teams if team)
        jobs.append(
            {
                "id": f"meta_{job_id}",
                "title": title,
                "location": location,
                "url": f"https://www.metacareers.com/jobs/{job_id}",
                "content": content,
            }
        )
    return jobs


def scrape_meta(company: CompanyConfig) -> list[dict[str, str]]:
    """Capture Meta's session-bound GraphQL job search passively."""

    target_company = dict(company)
    target_company["api_url"] = str(
        company.get("api_url") or META_JOBS_URL
    )
    result = NetworkInterceptScraper().scrape(
        company=target_company,
        target_url_pattern="/graphql",
        response_parser_fn=_meta_job_search_parser,
        request_method="POST",
    )
    company_id = str(company.get("company_id", "meta"))
    if result.status is ScrapeStatus.WAF_BLOCKED:
        LOGGER.warning("Meta interception was WAF-blocked for %s", company_id)
    elif result.status is ScrapeStatus.NO_JOBS:
        LOGGER.warning(
            "Meta interception returned no jobs for %s: %s",
            company_id,
            result.message,
        )
    elif result.status is ScrapeStatus.FAILED:
        LOGGER.error(
            "Meta interception failed for %s: %s",
            company_id,
            result.message,
        )
    return result.jobs


def _google_text(field: Any) -> str:
    """Extract HTML text from Google's positional two-item field."""

    if (
        isinstance(field, list)
        and len(field) > 1
        and isinstance(field[1], str)
    ):
        return field[1]
    return ""


def _google_job_parser(raw_data: Any) -> list[dict[str, str]]:
    """Normalize Google's ds:1 positional job arrays into shared records."""

    if (
        not isinstance(raw_data, list)
        or not raw_data
        or not isinstance(raw_data[0], list)
    ):
        return []

    jobs: list[dict[str, str]] = []
    for index, job in enumerate(raw_data[0]):
        try:
            if not isinstance(job, list):
                raise TypeError("Google job record must be a list")
            raw_locations = job[9]
            locations: list[str] = []
            if isinstance(raw_locations, list):
                for raw_location in raw_locations:
                    if (
                        isinstance(raw_location, (list, tuple))
                        and raw_location
                        and isinstance(raw_location[0], str)
                    ):
                        locations.append(raw_location[0])

            content = "\n\n".join(
                text
                for text in (
                    _google_text(job[3]),
                    _google_text(job[4]),
                    _google_text(job[10]),
                )
                if text
            )
            jobs.append(
                {
                    "id": f"google_{str(job[0])}",
                    "title": str(job[1]),
                    "location": ", ".join(locations),
                    "url": str(job[2]),
                    "content": content,
                }
            )
        except Exception as error:
            LOGGER.warning(
                "Skipping malformed Google job at index %s: %s",
                index,
                error,
            )
    return jobs


def scrape_google(company: CompanyConfig) -> list[dict[str, str]]:
    """Fetch bounded early-career and intern Google result pages."""

    configured_url = str(
        company.get("api_url") or GOOGLE_JOBS_BASE_URL
    ).strip()
    parsed_url = urlsplit(configured_url)
    base_url = urlunsplit(
        (
            parsed_url.scheme,
            parsed_url.netloc,
            parsed_url.path.rstrip("/"),
            "",
            "",
        )
    )
    embedded_scraper = EmbeddedJsonScraper()
    accumulated_jobs: list[dict[str, str]] = []
    company_id = str(company.get("company_id", "google"))
    # Once one page in this fetch has found real jobs, later empty/failed
    # pages (including the terminating NO_JOBS page of each variant) must
    # never overwrite that good artifact set on disk.
    has_found_jobs = False

    for variant in GOOGLE_QUERY_VARIANTS:
        page_number = 1
        while page_number <= GOOGLE_MAX_PAGES_PER_VARIANT:
            page_company = dict(company)
            page_company["api_url"] = (
                f"{base_url}?{variant}&page={page_number}"
            )
            result = embedded_scraper.scrape(
                company=page_company,
                data_parser_fn=_google_job_parser,
                write_diagnostics=not has_found_jobs,
            )
            if result.status is ScrapeStatus.SUCCESS and result.jobs:
                has_found_jobs = True

            if result.status is ScrapeStatus.FAILED:
                LOGGER.error(
                    "Google embedded extraction failed for %s: %s",
                    company_id,
                    result.message,
                )
                break
            if result.status is ScrapeStatus.WAF_BLOCKED:
                LOGGER.warning(
                    "Google embedded extraction was WAF-blocked for %s",
                    company_id,
                )
                break
            if result.status is ScrapeStatus.NO_JOBS or not result.jobs:
                break
            if result.status is not ScrapeStatus.SUCCESS:
                LOGGER.warning(
                    "Google extraction returned unexpected status %s for %s",
                    result.status,
                    company_id,
                )
                break

            accumulated_jobs.extend(result.jobs)
            page_number += 1
        else:
            LOGGER.warning(
                "Google pagination reached the %s-page safety limit for %s",
                GOOGLE_MAX_PAGES_PER_VARIANT,
                company_id,
            )

    jobs_by_id: dict[str, dict[str, str]] = {}
    for job in accumulated_jobs:
        jobs_by_id.setdefault(job["id"], job)
    return list(jobs_by_id.values())


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
            write_company_artifacts(
                company_id,
                source="api",
                primary_content=response.text,
                primary_extension="json",
                screenshot_bytes=None,
                notes={
                    "status": "success",
                    "message": "",
                    "job_count": len(jobs),
                    "sample_titles": extract_sample_titles(jobs),
                },
            )
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

    response_text: str | None = None
    try:
        response = requests.get(
            api_url,
            headers=IAI_REQUEST_HEADERS,
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        response_text = response.text
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError, TypeError) as error:
        LOGGER.error("IAI jobs API request failed: %s", error)
        write_company_artifacts(
            company_id,
            source="api",
            primary_content=response_text,
            primary_extension="json",
            screenshot_bytes=None,
            notes={
                "status": "failed",
                "message": f"{type(error).__name__}: {error}",
                "job_count": 0,
                "sample_titles": [],
            },
        )
        return []

    if not isinstance(payload, list):
        LOGGER.error(
            "IAI jobs API returned %s instead of a list",
            type(payload).__name__,
        )
        write_company_artifacts(
            company_id,
            source="api",
            primary_content=response_text,
            primary_extension="json",
            screenshot_bytes=None,
            notes={
                "status": "failed",
                "message": f"Unexpected payload type: {type(payload).__name__}",
                "job_count": 0,
                "sample_titles": [],
            },
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

    write_company_artifacts(
        company_id,
        source="api",
        primary_content=response_text,
        primary_extension="json",
        screenshot_bytes=None,
        notes={
            "status": "success" if jobs else "no_jobs",
            "message": "",
            "job_count": len(jobs),
            "sample_titles": extract_sample_titles(jobs),
        },
    )
    return jobs


def scrape_elbit(
    company: Mapping[str, Any],
) -> list[dict[str, str]]:
    """Normalize Elbit Systems' first-party JSON feed into shared records.

    The careers page is a Next.js shell whose job list never reaches the DOM
    as anchors (confirmed live), so this bypasses the frontend entirely and
    reads the same ``cron/jobs.json`` feed the page itself fetches.
    """

    company_id = (
        str(company.get("company_id", "elbit_systems")).strip()
        or "elbit_systems"
    )
    api_url = str(company.get("api_url", "")).strip()
    if not api_url:
        LOGGER.error("Elbit adapter requires an api_url")
        return []

    response_text: str | None = None
    try:
        response = requests.get(
            api_url,
            headers=IAI_REQUEST_HEADERS,
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        response_text = response.text
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError, TypeError) as error:
        LOGGER.error("Elbit jobs feed request failed: %s", error)
        write_company_artifacts(
            company_id,
            source="api",
            primary_content=response_text,
            primary_extension="json",
            screenshot_bytes=None,
            notes={
                "status": "failed",
                "message": f"{type(error).__name__}: {error}",
                "job_count": 0,
                "sample_titles": [],
            },
        )
        return []

    if not isinstance(payload, list):
        LOGGER.error(
            "Elbit jobs feed returned %s instead of a list",
            type(payload).__name__,
        )
        write_company_artifacts(
            company_id,
            source="api",
            primary_content=response_text,
            primary_extension="json",
            screenshot_bytes=None,
            notes={
                "status": "failed",
                "message": f"Unexpected payload type: {type(payload).__name__}",
                "job_count": 0,
                "sample_titles": [],
            },
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

        raw_job_id = item.get("jobId")
        title = str(item.get("jobTitle", "")).strip()
        if raw_job_id is None or not title:
            continue
        job_id = str(raw_job_id).strip()
        if not job_id:
            continue

        raw_description = str(item.get("description") or "")
        content = BeautifulSoup(
            html.unescape(raw_description),
            "lxml",
        ).get_text(" ", strip=True)

        jobs.append(
            {
                "id": f"{company_id}_{job_id}",
                "title": title,
                "location": str(item.get("area") or "").strip(),
                "url": urljoin(
                    origin,
                    f"Recruitment-Page/?jobId={quote(job_id, safe='')}",
                ),
                "content": content,
            }
        )

    write_company_artifacts(
        company_id,
        source="api",
        primary_content=response_text,
        primary_extension="json",
        screenshot_bytes=None,
        notes={
            "status": "success" if jobs else "no_jobs",
            "message": "",
            "job_count": len(jobs),
            "sample_titles": extract_sample_titles(jobs),
        },
    )
    return jobs


AMDOCS_PAGE_SIZE = 10
AMDOCS_MAX_PAGES = 50


def scrape_amdocs(
    company: Mapping[str, Any],
) -> list[dict[str, str]]:
    """Paginate Amdocs' pcsx search API and let downstream filters scope it.

    The frontend's own ``location=israel`` query param returns zero results
    even from a real authenticated browser session (confirmed live) --
    verified this is not a CSRF/auth gap, the backend genuinely has nothing
    tagged for that filter today. So this fetches the domain unconditionally,
    same as ``scrape_iai``, and relies on the orchestrator's existing
    ``location_filters``/``is_in_location`` to scope results to Israel.
    """

    company_id = (
        str(company.get("company_id", "amdocs")).strip() or "amdocs"
    )
    api_url = str(company.get("api_url", "")).strip()
    if not api_url:
        LOGGER.error("Amdocs adapter requires an api_url")
        return []

    parsed_api_url = urlsplit(api_url)
    origin = urlunsplit(
        (parsed_api_url.scheme, parsed_api_url.netloc, "/", "", "")
    )

    jobs: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    first_page_response_text: str | None = None
    fetch_error = ""
    start = 0

    for _page_number in range(AMDOCS_MAX_PAGES):
        try:
            response = requests.get(
                api_url,
                params={"domain": "amdocs.com", "start": start},
                headers=IAI_REQUEST_HEADERS,
                timeout=HTTP_TIMEOUT_SECONDS,
            )
            if first_page_response_text is None:
                first_page_response_text = response.text
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError, TypeError) as error:
            LOGGER.error(
                "Amdocs search request failed at start=%s: %s",
                start,
                error,
            )
            fetch_error = f"{type(error).__name__}: {error}"
            break

        data = payload.get("data") if isinstance(payload, Mapping) else None
        positions = (
            data.get("positions") if isinstance(data, Mapping) else None
        )
        if not isinstance(positions, list) or not positions:
            break

        for item in positions:
            if not isinstance(item, Mapping):
                continue
            raw_job_id = item.get("id")
            title = str(item.get("name", "")).strip()
            if raw_job_id is None or not title:
                continue
            job_id = str(raw_job_id).strip()
            if not job_id or job_id in seen_ids:
                continue
            seen_ids.add(job_id)

            raw_locations = item.get("standardizedLocations")
            if not isinstance(raw_locations, list) or not raw_locations:
                raw_locations = item.get("locations")
            locations = (
                [str(value).strip() for value in raw_locations if value]
                if isinstance(raw_locations, list)
                else []
            )

            position_url = str(item.get("positionUrl", "")).strip()
            jobs.append(
                {
                    "id": f"{company_id}_{job_id}",
                    "title": title,
                    "location": ", ".join(locations),
                    "url": (
                        urljoin(origin, position_url)
                        if position_url
                        else origin
                    ),
                    "content": "",
                }
            )

        if len(positions) < AMDOCS_PAGE_SIZE:
            break
        start += len(positions)

    write_company_artifacts(
        company_id,
        source="api",
        primary_content=first_page_response_text,
        primary_extension="json",
        screenshot_bytes=None,
        notes={
            "status": "failed" if fetch_error else (
                "success" if jobs else "no_jobs"
            ),
            "message": fetch_error,
            "job_count": len(jobs),
            "sample_titles": extract_sample_titles(jobs),
        },
    )
    return jobs


_COMEET_POSITIONS_DATA_PATTERN = re.compile(
    r"COMPANY_POSITIONS_DATA\s*=\s*(\[.*?\])\s*;", re.S
)
_COMEET_INIT_CONFIG_PATTERN = re.compile(
    r"COMEET\.init\(\s*\{(.*?)\}\s*\)", re.S
)
_COMEET_JOB_UID_IN_URL_PATTERN = re.compile(r"/([0-9A-Za-z]{1,3}\.[0-9A-Za-z]{2,5})(?:/|$)")


def _comeet_positions_from_html(html_text: str) -> list[Mapping[str, Any]] | None:
    """Parse Comeet's inline ``COMPANY_POSITIONS_DATA`` array, when present.

    Every genuinely Comeet-hosted board (``comeet.com/jobs/<name>/<uid>``)
    renders this JS array directly into the page on first load -- a plain
    GET returns it, no browser or separate API call required. Returns
    ``None`` (not an empty list) when the marker is absent, so callers can
    distinguish "this response uses a different Comeet embed shape" from
    "this board genuinely has zero open positions."
    """

    match = _COMEET_POSITIONS_DATA_PATTERN.search(html_text)
    if match is None:
        return None
    try:
        data = json.loads(match.group(1))
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, list):
        return None
    return [item for item in data if isinstance(item, Mapping)]


def _comeet_board_url_candidates(
    html_text: str,
    configured_url: str,
) -> list[str]:
    """Derive candidate direct Comeet board URLs from a widget's own config.

    Some companies embed Comeet as a JS widget (``COMEET.init({...})``) on
    their own careers page instead of hosting directly on comeet.com. The
    widget config names its own ``company-uid`` and a ``company-name`` --
    the exact two path segments Comeet's own board URLs use -- but the
    slug Comeet actually assigned is not always a plain lowercase/hyphenate
    of that display name (confirmed live: Moon Active's real slug is
    "moonactive", not "moon-active", which instead 302-redirects to
    Comeet's homepage). Neither candidate here is invented: one comes from
    the widget's own declared name, the other from the same domain the
    company already configured as its careers page. Both are real
    identifiers the company itself asserts; the caller fetches and
    validates each in turn, and a name mismatch degrades to no candidate
    working rather than ever trusting an unconfirmed response.
    """

    match = _COMEET_INIT_CONFIG_PATTERN.search(html_text)
    if match is None:
        return []
    config_text = match.group(1)
    uid_match = re.search(r'"company-uid"\s*:\s*"([^"]+)"', config_text)
    if uid_match is None:
        return []
    company_uid = uid_match.group(1).strip()
    if not company_uid:
        return []

    slug_candidates: list[str] = []
    name_match = re.search(r'"company-name"\s*:\s*"([^"]+)"', config_text)
    if name_match is not None:
        name_slug = name_match.group(1).strip().casefold().replace(" ", "-")
        if name_slug:
            slug_candidates.append(name_slug)
    domain_host = urlsplit(configured_url).netloc.casefold()
    domain_slug = re.sub(r"^www\.", "", domain_host).split(".")[0]
    if domain_slug and domain_slug not in slug_candidates:
        slug_candidates.append(domain_slug)

    return [
        "https://www.comeet.com/jobs/"
        f"{quote(slug, safe='-')}/{quote(company_uid, safe='.')}"
        for slug in slug_candidates
    ]


def _comeet_job_from_position_data(
    item: Mapping[str, Any],
    company_id: str,
) -> dict[str, str] | None:
    """Normalize one ``COMPANY_POSITIONS_DATA`` entry into a shared record."""

    raw_uid = item.get("uid")
    title = str(item.get("name") or "").strip()
    if not raw_uid or not title:
        return None
    job_uid = str(raw_uid).strip()
    if not job_uid:
        return None

    location_value = item.get("location")
    location = (
        _join_distinct_text(
            location_value.get("city"),
            location_value.get("state"),
            location_value.get("name"),
        )
        if isinstance(location_value, Mapping)
        else ""
    )

    job_url = str(
        item.get("url_active_page") or item.get("url_comeet_hosted_page") or ""
    ).strip()

    content_parts: list[Any] = []
    custom_fields = item.get("custom_fields")
    if isinstance(custom_fields, Mapping):
        details = custom_fields.get("details")
        if isinstance(details, list):
            content_parts.extend(
                detail.get("value")
                for detail in details
                if isinstance(detail, Mapping)
            )
    content = normalize_job_content(*content_parts)

    return {
        "id": f"{company_id}_{job_uid}",
        "title": title,
        "location": location,
        "url": job_url,
        "content": content,
    }


def _comeet_jobs_from_dom(
    html_text: str,
    base_url: str,
    company_id: str,
) -> list[dict[str, str]]:
    """Extract jobs from Comeet's WordPress-plugin embed as a last resort.

    This shape server-renders ``.comeet-position`` elements directly into
    the page instead of exposing ``COMPANY_POSITIONS_DATA``, so there is no
    structured location or description field to read -- only what is
    visible in the listing itself, matching the DOM-fallback shape used
    elsewhere in this module when no richer API response is available.
    """

    soup = BeautifulSoup(html_text, "lxml")
    jobs: list[dict[str, str]] = []
    seen_urls: set[str] = set()

    for element in soup.select(".comeet-position"):
        # The plugin renders this shape both ways: sometimes ".comeet-position"
        # is itself the anchor (confirmed live on Nuvoton), sometimes it is a
        # wrapper div around a nested one (confirmed live on ChargeAfter).
        link = element if element.has_attr("href") else element.select_one("a[href]")
        title_element = element.select_one(".comeet-position-name")
        if link is None or title_element is None:
            continue
        title = title_element.get_text(strip=True)
        href = str(link.get("href", "")).strip()
        if not title or not href:
            continue

        full_url = urljoin(base_url, href)
        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)

        meta_element = element.select_one(".comeet-position-meta")
        location = (
            meta_element.get_text(" ", strip=True) if meta_element else ""
        )
        uid_match = _COMEET_JOB_UID_IN_URL_PATTERN.search(full_url)
        job_id = (
            uid_match.group(1)
            if uid_match is not None
            else hashlib.sha256(full_url.encode("utf-8")).hexdigest()[:16]
        )
        jobs.append(
            {
                "id": f"{company_id}_{job_id}",
                "title": title,
                "location": location,
                "url": full_url,
                "content": "",
            }
        )

    return jobs


def _comeet_failure_status(error: requests.RequestException) -> ScrapeStatus:
    """Classify an HTTP block separately from other Comeet failures."""

    response = getattr(error, "response", None)
    status_code = response.status_code if response is not None else None
    if status_code in COMEET_BLOCKING_HTTP_STATUS_CODES:
        return ScrapeStatus.WAF_BLOCKED
    return ScrapeStatus.FAILED


def scrape_comeet(company: CompanyConfig) -> ScrapeResult:
    """Fetch and normalize jobs from any of Comeet's three embed shapes.

    Comeet integrations found across the catalogue take one of three
    concrete shapes, tried here in order of data richness:

    1. A direct Comeet-hosted board (``api_url`` already points at
       ``comeet.com/jobs/<name>/<uid>``) renders every open position into
       an inline ``COMPANY_POSITIONS_DATA`` JS array on first load -- one
       plain GET, no browser needed.
    2. A company's own careers page embeds Comeet as a JS widget
       (``COMEET.init({...})``). That config names the exact board from
       shape 1, so it is derived and fetched next.
    3. A company's own careers page uses Comeet's WordPress plugin, which
       server-renders ``.comeet-position`` elements with no separate data
       call; those are DOM-scraped as a last resort (job description is
       not available without a per-job follow-up this adapter does not
       perform, same limitation as other DOM-only extraction in this
       module).

    A single ``ats_type: comeet`` adapter serves every company regardless
    of which shape it uses -- ``api_url`` is the only per-company input.
    """

    company_id = str(company.get("company_id", "")).strip()
    api_url = str(company.get("api_url", "")).strip()
    if not company_id or not api_url:
        message = "Comeet adapter requires company_id and api_url."
        LOGGER.error(message)
        return ScrapeResult(
            status=ScrapeStatus.FAILED,
            jobs=[],
            message=message,
        )

    response_text: str | None = None
    fetch_error = ""
    fetch_error_status: ScrapeStatus | None = None
    try:
        response = requests.get(
            api_url,
            headers=COMEET_REQUEST_HEADERS,
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        response_text = response.text
        response.raise_for_status()
    except requests.RequestException as error:
        status = _comeet_failure_status(error)
        LOGGER.error("Comeet request failed for %s: %s", company_id, error)
        write_company_artifacts(
            company_id,
            source="api",
            primary_content=response_text,
            primary_extension="html",
            screenshot_bytes=None,
            notes={
                "status": status.value,
                "message": f"{type(error).__name__}: {error}",
                "job_count": 0,
                "sample_titles": [],
            },
        )
        return ScrapeResult(
            status=status,
            jobs=[],
            message=f"{type(error).__name__}: {error}",
        )

    positions = _comeet_positions_from_html(response_text)

    if positions is None:
        for board_url in _comeet_board_url_candidates(response_text, api_url):
            if board_url == api_url:
                continue
            try:
                board_response = requests.get(
                    board_url,
                    headers=COMEET_REQUEST_HEADERS,
                    timeout=HTTP_TIMEOUT_SECONDS,
                )
                board_response.raise_for_status()
            except requests.RequestException as error:
                LOGGER.warning(
                    "Comeet derived board request failed for %s (%s): %s",
                    company_id,
                    board_url,
                    error,
                )
                fetch_error = f"derived board request failed: {error}"
                candidate_status = _comeet_failure_status(error)
                if fetch_error_status is not ScrapeStatus.WAF_BLOCKED:
                    fetch_error_status = candidate_status
                continue
            # A wrong slug 302s to Comeet's own homepage rather than a 4xx,
            # so only a response that actually contains position data counts
            # as a confirmed candidate; anything else moves on to the next.
            candidate_positions = _comeet_positions_from_html(board_response.text)
            if candidate_positions is not None:
                positions = candidate_positions
                fetch_error = ""
                break

    if positions is not None:
        jobs = [
            job
            for item in positions
            if (job := _comeet_job_from_position_data(item, company_id))
            is not None
        ]
    else:
        jobs = _comeet_jobs_from_dom(response_text, api_url, company_id)

    if jobs:
        status = ScrapeStatus.SUCCESS
    elif fetch_error_status is not None:
        status = fetch_error_status
    else:
        status = ScrapeStatus.NO_JOBS

    write_company_artifacts(
        company_id,
        source="api",
        primary_content=response_text,
        primary_extension="html",
        screenshot_bytes=None,
        notes={
            "status": status.value,
            "message": fetch_error,
            "job_count": len(jobs),
            "sample_titles": extract_sample_titles(jobs),
        },
    )
    return ScrapeResult(
        status=status,
        jobs=jobs,
        message=fetch_error,
    )


_WORKABLE_ACCOUNT_PATTERN = re.compile(r"/accounts/([^/]+)/jobs")


def scrape_workable(company: CompanyConfig) -> list[dict[str, str]]:
    """Fetch and normalize jobs from a Workable job-board API endpoint.

    Workable's public listing API (``apply.workable.com/api/v3/accounts/
    <token>/jobs``) requires a POST with an empty JSON body -- a plain GET
    returns 404, which is easy to mistake for "no such account." The
    account token doubles as the path segment for Workable's public job
    pages (``apply.workable.com/<token>/j/<shortcode>/``), so it is
    extracted once from ``api_url`` rather than requiring a second config
    field.
    """

    company_id = str(company.get("company_id", "")).strip()
    api_url = str(company.get("api_url", "")).strip()
    if not company_id or not api_url:
        LOGGER.error("Workable adapter requires an api_url")
        return []

    account_match = _WORKABLE_ACCOUNT_PATTERN.search(api_url)
    account = account_match.group(1) if account_match else None

    response_text: str | None = None
    try:
        response = requests.post(
            api_url,
            json={},
            headers={**IAI_REQUEST_HEADERS, "Content-Type": "application/json"},
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        response_text = response.text
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as error:
        LOGGER.error("Workable request failed for %s: %s", company_id, error)
        write_company_artifacts(
            company_id,
            source="api",
            primary_content=response_text,
            primary_extension="json",
            screenshot_bytes=None,
            notes={
                "status": "failed",
                "message": f"{type(error).__name__}: {error}",
                "job_count": 0,
                "sample_titles": [],
            },
        )
        return []

    results = payload.get("results") if isinstance(payload, Mapping) else None
    if not isinstance(results, list):
        LOGGER.error(
            "Workable response for %s had no results list", company_id
        )
        write_company_artifacts(
            company_id,
            source="api",
            primary_content=response_text,
            primary_extension="json",
            screenshot_bytes=None,
            notes={
                "status": "failed",
                "message": "Unexpected payload shape: no results list",
                "job_count": 0,
                "sample_titles": [],
            },
        )
        return []

    jobs: list[dict[str, str]] = []
    for item in results:
        if not isinstance(item, Mapping):
            continue
        # shortcode is required, not just preferred: it is the only field
        # that builds a working public job URL, and a job with no URL is
        # not useful downstream.
        raw_shortcode = item.get("shortcode")
        title = str(item.get("title") or "").strip()
        if not raw_shortcode or not title:
            continue
        job_id = str(raw_shortcode).strip()
        if not job_id:
            continue

        location_value = item.get("location")
        location = (
            _join_distinct_text(
                location_value.get("city"),
                location_value.get("region"),
                location_value.get("country"),
            )
            if isinstance(location_value, Mapping)
            else ""
        )

        job_url = (
            f"https://apply.workable.com/{account}/j/{job_id}/"
            if account
            else ""
        )

        jobs.append(
            {
                "id": f"{company_id}_{job_id}",
                "title": title,
                "location": location,
                "url": job_url,
                "content": "",
            }
        )

    write_company_artifacts(
        company_id,
        source="api",
        primary_content=response_text,
        primary_extension="json",
        screenshot_bytes=None,
        notes={
            "status": "success" if jobs else "no_jobs",
            "message": "",
            "job_count": len(jobs),
            "sample_titles": extract_sample_titles(jobs),
        },
    )
    return jobs


ORC_PAGE_SIZE = 25
ORC_MAX_PAGES = 40


def _orc_location(item: Mapping[str, Any]) -> str:
    """Join a requisition's primary and secondary locations defensively."""

    locations: list[str] = []
    primary = str(item.get("PrimaryLocation") or "").strip()
    if primary:
        locations.append(primary)

    raw_secondary = item.get("secondaryLocations")
    if isinstance(raw_secondary, list):
        for entry in raw_secondary:
            if not isinstance(entry, Mapping):
                continue
            name = str(entry.get("Name") or "").strip()
            if name and name not in locations:
                locations.append(name)

    return ", ".join(locations)


def scrape_oracle_rc(
    company: CompanyConfig,
) -> list[dict[str, str]]:
    """Fetch Oracle Recruiting Cloud requisitions via its public REST API.

    Generic across any ORC tenant (Oracle itself, Akamai, and any future
    company on the same platform): the REST backend lives on
    ``*.oraclecloud.com``, a completely different host than each tenant's
    own WAF-protected careers frontend. Confirmed live: Akamai's own edge
    blocks ``jobs.akamai.com`` outright, but its Oracle Cloud backend on
    ``fa-extu-saasfaprod1.fa.ocs.oraclecloud.com`` answers unauthenticated
    requests with a plain 200. ``api_url`` and ``oracle_site_number`` are
    tenant-specific and come from company config, matching every other
    custom adapter in this module; the fetch/pagination logic here is
    fully generic.

    Scopes the search server-side with a ``keyword`` finder param (the
    company's first configured ``location_filters`` entry, "Israel" for
    every company we care about) to avoid paginating a tenant's entire
    global requisition pool -- Oracle's own site currently has over 2,000
    open roles worldwide, only a handful in Israel. The keyword match can
    still produce false positives (confirmed live: an Akamai US-based role
    matched on an incidental "Israel" mention), so the orchestrator's
    existing ``location_filters``/``is_in_location`` check downstream is
    still required and remains the authoritative filter.
    """

    company_id = str(company.get("company_id", "")).strip()
    api_url = str(company.get("api_url", "")).strip()
    site_number = str(company.get("oracle_site_number", "")).strip()
    if not company_id or not api_url or not site_number:
        LOGGER.error(
            "Oracle Recruiting Cloud adapter requires api_url and "
            "oracle_site_number"
        )
        return []

    careers_url = str(company.get("oracle_careers_url", "")).strip()
    configured_filters = company.get("location_filters")
    keyword = (
        str(configured_filters[0])
        if isinstance(configured_filters, list) and configured_filters
        else "Israel"
    )

    jobs: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    first_page_response_text: str | None = None
    fetch_error = ""
    offset = 0

    for _page_number in range(ORC_MAX_PAGES):
        finder = (
            f"findReqs;siteNumber={site_number},keyword={keyword},"
            f"limit={ORC_PAGE_SIZE},offset={offset}"
        )
        try:
            response = requests.get(
                api_url,
                params={
                    "onlyData": "true",
                    "expand": (
                        "requisitionList.secondaryLocations,"
                        "requisitionList.workLocation"
                    ),
                    "finder": finder,
                },
                headers=IAI_REQUEST_HEADERS,
                timeout=HTTP_TIMEOUT_SECONDS,
            )
            if first_page_response_text is None:
                first_page_response_text = response.text
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError, TypeError) as error:
            LOGGER.error(
                "Oracle Recruiting Cloud request failed for %s at "
                "offset=%s: %s",
                company_id,
                offset,
                error,
            )
            fetch_error = f"{type(error).__name__}: {error}"
            break

        items = payload.get("items") if isinstance(payload, Mapping) else None
        result = (
            items[0]
            if isinstance(items, list) and items and isinstance(items[0], Mapping)
            else None
        )
        requisitions = (
            result.get("requisitionList") if result is not None else None
        )
        if not isinstance(requisitions, list) or not requisitions:
            break

        total_jobs = result.get("TotalJobsCount") if result else None
        for item in requisitions:
            if not isinstance(item, Mapping):
                continue
            raw_job_id = item.get("Id")
            title = str(item.get("Title", "")).strip()
            if raw_job_id is None or not title:
                continue
            job_id = str(raw_job_id).strip()
            if not job_id or job_id in seen_ids:
                continue
            seen_ids.add(job_id)

            jobs.append(
                {
                    "id": f"{company_id}_{job_id}",
                    "title": title,
                    "location": _orc_location(item),
                    "url": (
                        f"{careers_url}{job_id}" if careers_url else ""
                    ),
                    "content": str(item.get("ShortDescriptionStr") or ""),
                }
            )

        next_offset = offset + len(requisitions)
        if len(requisitions) < ORC_PAGE_SIZE or (
            isinstance(total_jobs, int) and next_offset >= total_jobs
        ):
            break
        offset = next_offset

    write_company_artifacts(
        company_id,
        source="api",
        primary_content=first_page_response_text,
        primary_extension="json",
        screenshot_bytes=None,
        notes={
            "status": "failed" if fetch_error else (
                "success" if jobs else "no_jobs"
            ),
            "message": fetch_error,
            "job_count": len(jobs),
            "sample_titles": extract_sample_titles(jobs),
        },
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
    first_page_response_text: str | None = None
    fetch_error: str = ""

    for _page_number in range(THALES_PHENOM_MAX_PAGES):
        try:
            response = requests.post(
                api_url,
                json=_thales_phenom_payload(page_offset),
                headers=THALES_REQUEST_HEADERS,
                timeout=HTTP_TIMEOUT_SECONDS,
            )
            if first_page_response_text is None:
                first_page_response_text = response.text
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
            fetch_error = f"{type(error).__name__}: {error}"
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

    write_company_artifacts(
        company_id,
        source="api",
        primary_content=first_page_response_text,
        primary_extension="json",
        screenshot_bytes=None,
        notes={
            "status": "failed" if fetch_error else (
                "success" if jobs else "no_jobs"
            ),
            "message": fetch_error,
            "job_count": len(jobs),
            "sample_titles": extract_sample_titles(jobs),
        },
    )
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

    response_text = None
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response_text = response.text
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

        write_company_artifacts(
            str(company_id),
            source="api",
            primary_content=response_text,
            primary_extension="html",
            screenshot_bytes=None,
            notes={
                "status": "success" if jobs else "no_jobs",
                "message": "",
                "job_count": len(jobs),
                "sample_titles": extract_sample_titles(jobs),
            },
        )
        return jobs

    except Exception as e:
        LOGGER.error("Error scraping HTML for %s: %s", company_id, e)
        write_company_artifacts(
            str(company_id),
            source="api",
            primary_content=response_text,
            primary_extension="html",
            screenshot_bytes=None,
            notes={
                "status": "failed",
                "message": f"{type(e).__name__}: {e}",
                "job_count": 0,
                "sample_titles": [],
            },
        )
        return []

def scrape_universal_playwright(
    company: dict[str, Any],
) -> list[dict[str, str]]:
    """Run the OOP Playwright scraper while preserving the legacy API."""

    company_id = str(company.get("company_id", "unknown"))
    LOGGER.info("🕵️ מפעיל סורק אוניברסלי (Playwright) עבור %s...", company_id)

    result = PlaywrightJobScraper().scrape(company)
    if result.status is ScrapeStatus.WAF_BLOCKED:
        LOGGER.warning(
            "🛡️ %s נחסם על ידי אתגר WAF: %s. בדוק את logs/api_discovery_log.json.",
            company_id,
            result.message,
        )
    elif result.status is ScrapeStatus.NO_JOBS:
        LOGGER.warning("⚠️ %s החזיר 0 משרות: %s", company_id, result.message)
    elif result.status is ScrapeStatus.FAILED:
        LOGGER.error(
            "❌ שגיאה בסריקה אוניברסלית של %s: %s",
            company_id,
            result.message,
        )

    return result.jobs
