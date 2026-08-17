"""HTTP client and normalization for mapping-driven JSON ATS sources."""

from __future__ import annotations

import time
from typing import Any, Mapping

import requests
from bs4 import BeautifulSoup

from scrapers.api.mappings import AtsMapping

HTTP_TIMEOUT_SECONDS = 15
RETRY_DELAY_SECONDS = 0.5
MAX_RETRY_DELAY_SECONDS = 5.0
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
    """Send one ATS request and retry one transient failure."""

    method = mapping.method.upper()
    if method not in {"GET", "POST"}:
        raise ValueError(f"Unsupported ATS request method: {method}")

    attempt = 0
    while True:
        try:
            if method == "GET":
                response = requests.get(api_url, **request_kwargs)
            else:
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
            response.raise_for_status()
            return response
        except (
            requests.exceptions.HTTPError,
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
        ) as error:
            error_response = getattr(error, "response", None)
            status_code = (
                error_response.status_code
                if error_response is not None
                else None
            )
            is_http_error = isinstance(
                error,
                requests.exceptions.HTTPError,
            )
            is_retryable_error = (
                not is_http_error
                or status_code in RETRYABLE_HTTP_STATUS_CODES
            )
            should_retry = (
                is_retryable_error
                and attempt < MAX_REQUEST_ATTEMPTS - 1
            )
            if not should_retry:
                raise
            delay_seconds = _retry_delay_seconds(error_response)
            reason = (
                f"API status {status_code}"
                if status_code is not None
                else type(error).__name__
            )
            print(
                f"Retrying {company_id} once after {reason}."
            )
            time.sleep(delay_seconds)
            attempt += 1


def _retry_delay_seconds(
    response: requests.Response | None,
) -> float:
    """Return a bounded numeric Retry-After or the default retry delay."""

    if response is None or not isinstance(response.headers, Mapping):
        return RETRY_DELAY_SECONDS
    retry_after = response.headers.get("Retry-After")
    if retry_after is None:
        return RETRY_DELAY_SECONDS
    try:
        delay_seconds = max(float(str(retry_after).strip()), 0.0)
        return min(delay_seconds, MAX_RETRY_DELAY_SECONDS)
    except ValueError:
        return RETRY_DELAY_SECONDS


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
