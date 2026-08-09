"""Declarative field mappings for JSON-based applicant tracking systems."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping


@dataclass(frozen=True)
class AtsMapping:
    """Describe how one JSON ATS is requested and normalized."""

    envelope_key: str
    id_fn: Callable[[Mapping[str, Any]], Any]
    title_fn: Callable[[Mapping[str, Any]], Any]
    location_fn: Callable[[Mapping[str, Any]], Any]
    url_fn: Callable[[Mapping[str, Any], str], Any]
    content_fields_fn: Callable[[Mapping[str, Any]], tuple[Any, ...]]
    method: str = "GET"
    headers: dict[str, str] | None = None
    payload_fn: Callable[[dict], dict[str, Any]] | None = None
    base_url_fn: Callable[[dict], str] | None = None
    http_error_status_map: frozenset[int] = field(
        default_factory=frozenset
    )


ATS_FIELD_MAP: dict[str, AtsMapping] = {
    "greenhouse": AtsMapping(
        envelope_key="jobs",
        id_fn=lambda job: job.get("id"),
        title_fn=lambda job: job.get("title", ""),
        location_fn=lambda job: (
            (job.get("location") or {}).get("name", "")
        ),
        url_fn=lambda job, _base_url: job.get("absolute_url", ""),
        content_fields_fn=lambda job: (
            job.get("content"),
            job.get("description"),
        ),
    ),
    "amazon_jobs": AtsMapping(
        envelope_key="jobs",
        id_fn=lambda job: job.get("id_ic", job.get("id", "")),
        title_fn=lambda job: job.get("title", ""),
        location_fn=lambda job: job.get("city", ""),
        url_fn=lambda job, base_url: (
            f"{base_url}{job.get('job_path', '')}"
        ),
        content_fields_fn=lambda job: (
            job.get("description"),
            job.get("basic_qualifications"),
            job.get("preferred_qualifications"),
        ),
        base_url_fn=lambda _company: "https://www.amazon.jobs",
    ),
    "smartrecruiters": AtsMapping(
        envelope_key="content",
        id_fn=lambda job: job.get("id", ""),
        title_fn=lambda job: job.get("name", ""),
        location_fn=lambda job: (
            (job.get("location") or {}).get("city", "")
        ),
        url_fn=lambda job, _base_url: job.get("ref", ""),
        content_fields_fn=lambda job: (
            job.get("jobAd"),
            job.get("description"),
        ),
    ),
    "ashby": AtsMapping(
        envelope_key="jobs",
        id_fn=lambda job: job.get("id", ""),
        title_fn=lambda job: job.get("title", ""),
        location_fn=lambda job: job.get("location", ""),
        url_fn=lambda job, _base_url: job.get("jobUrl", ""),
        content_fields_fn=lambda job: (
            job.get("descriptionPlain"),
            job.get("descriptionHtml"),
            job.get("description"),
        ),
    ),
    "workday": AtsMapping(
        envelope_key="jobPostings",
        id_fn=lambda job: job.get("bulletinId", job.get("id", "")),
        title_fn=lambda job: job.get("title", ""),
        location_fn=lambda job: job.get("locationsText", ""),
        url_fn=lambda job, base_url: (
            f"{base_url}{job.get('externalPath', '')}"
        ),
        content_fields_fn=lambda job: (
            job.get("jobDescription"),
            job.get("description"),
        ),
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        payload_fn=lambda _company: {
            "limit": 20,
            "offset": 0,
            "appliedFacets": {},
        },
        base_url_fn=lambda company: str(
            company.get("api_url", "")
        ).split("/wday/cxs")[0],
        http_error_status_map=frozenset({401, 403, 422}),
    ),
}
ATS_FIELD_MAP["greenhouse_eu"] = ATS_FIELD_MAP["greenhouse"]
