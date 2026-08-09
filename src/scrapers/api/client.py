"""HTTP client and normalization for mapping-driven JSON ATS sources."""

from __future__ import annotations

from typing import Any, Mapping

import requests
from bs4 import BeautifulSoup

from scrapers.api.mappings import AtsMapping

HTTP_TIMEOUT_SECONDS = 15


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


def fetch_ats_jobs(
    company: dict,
    mapping: AtsMapping,
) -> list[dict]:
    """Fetch and normalize jobs for one mapping-driven JSON ATS."""

    api_url = company.get("api_url")
    company_id = company.get("company_id")
    ats_type = company.get("ats_type")
    request_kwargs: dict[str, Any] = {
        "timeout": HTTP_TIMEOUT_SECONDS,
    }
    if mapping.headers is not None:
        request_kwargs["headers"] = mapping.headers

    try:
        method = mapping.method.upper()
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

        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, Mapping):
            return []

        items = payload.get(mapping.envelope_key, [])
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
