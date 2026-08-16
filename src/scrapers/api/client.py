"""HTTP client and normalization for mapping-driven JSON ATS sources."""

from __future__ import annotations

import time
from typing import Any, Mapping

import requests
from bs4 import BeautifulSoup

from scrapers.api.mappings import AtsMapping

HTTP_TIMEOUT_SECONDS = 15
RETRY_DELAY_SECONDS = 0.5
MAX_REQUEST_ATTEMPTS = 2
RETRYABLE_HTTP_STATUS_CODES = frozenset({429, 520, 521, 522, 523, 524})
DEFAULT_REQUEST_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/152.0.0.0 Safari/537.36"
    ),
}


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


def _request_jobs_response(
    api_url: str,
    company_id: str,
    company: dict[str, Any],
    mapping: AtsMapping,
    request_kwargs: dict[str, Any],
) -> requests.Response:
    """Send one ATS request and retry one Cloudflare edge failure."""

    method = mapping.method.upper()
    for attempt in range(MAX_REQUEST_ATTEMPTS):
        if method == "GET":
            response = requests.get(api_url, **request_kwargs)
        elif method == "POST":
            payload = (
                mapping.payload_fn(company)
                if mapping.payload_fn is not None
                else {}
            )
            response = requests.post(
                api_url,
                json=payload,
                **request_kwargs,
            )
        else:
            raise ValueError(f"Unsupported ATS request method: {method}")

        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError:
            should_retry = (
                response.status_code in RETRYABLE_HTTP_STATUS_CODES
                and attempt == 0
            )
            if not should_retry:
                raise
            print(
                f"Retrying {company_id} once after API status "
                f"{response.status_code}."
            )
            time.sleep(RETRY_DELAY_SECONDS)
            continue
        return response

    raise RuntimeError("ATS request retry loop exhausted unexpectedly")


def fetch_ats_jobs(
    company: dict[str, Any],
    mapping: AtsMapping,
) -> list[dict]:
    """Fetch and normalize jobs for one mapping-driven JSON ATS."""

    api_url = str(company.get("api_url", ""))
    company_id = str(company.get("company_id", ""))
    ats_type = company.get("ats_type")
    request_headers = dict(DEFAULT_REQUEST_HEADERS)
    if mapping.headers is not None:
        request_headers.update(mapping.headers)
    request_kwargs: dict[str, Any] = {
        "headers": request_headers,
        "timeout": HTTP_TIMEOUT_SECONDS,
    }

    try:
        response = _request_jobs_response(
            api_url=api_url,
            company_id=company_id,
            company=company,
            mapping=mapping,
            request_kwargs=request_kwargs,
        )
        payload = response.json()
        if mapping.envelope_key is None:
            items = payload
        elif isinstance(payload, Mapping):
            items = payload.get(mapping.envelope_key, [])
        else:
            return []
        if not isinstance(items, list):
            return []

        base_url = (
            mapping.base_url_fn(company)
            if mapping.base_url_fn is not None
            else ""
        )
        jobs: list[dict] = []
        for item in items:
            if not isinstance(item, Mapping):
                continue
            raw_id = mapping.id_fn(item)
            title = mapping.title_fn(item)
            location = mapping.location_fn(item)
            job_url = mapping.url_fn(item, base_url)
            jobs.append(
                {
                    "id": f"{company_id}_{raw_id}",
                    "title": str(title or ""),
                    "location": str(location or ""),
                    "url": str(job_url or ""),
                    "content": normalize_job_content(
                        *mapping.content_fields_fn(item)
                    ),
                }
            )
        return jobs
    except requests.exceptions.HTTPError as error:
        response = error.response
        status_code = (
            response.status_code if response is not None else None
        )
        if status_code in mapping.http_error_status_map:
            print(
                f"⚠️ {company_id} API returned {status_code} "
                "(Requires specific payload or auth)."
            )
        elif status_code is not None:
            print(f"❌ Network error on {company_id}: {status_code}")
        else:
            print(f"❌ Error scanning {ats_type} {company_id}: {error}")
        return []
    except Exception as error:
        print(f"❌ Error scanning {ats_type} {company_id}: {error}")
        return []
