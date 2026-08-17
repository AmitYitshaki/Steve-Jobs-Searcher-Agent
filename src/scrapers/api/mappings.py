"""Declarative field mappings for JSON-based applicant tracking systems."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping


@dataclass(frozen=True)
class AtsPagination:
    """Describe offset pagination for one mapping-driven ATS."""

    page_size: int
    total_fn: Callable[[Mapping[str, Any]], Any]
    offset_key: str = "offset"
    max_pages: int = 100


@dataclass(frozen=True)
class AtsMapping:
    """Describe how one JSON ATS is requested and normalized."""

    id_fn: Callable[[Mapping[str, Any]], Any]
    title_fn: Callable[[Mapping[str, Any]], Any]
    location_fn: Callable[[Mapping[str, Any]], Any]
    url_fn: Callable[[Mapping[str, Any], str], Any]
    content_fields_fn: Callable[[Mapping[str, Any]], tuple[Any, ...]]
    envelope_key: str | None = None
    method: str = "GET"
    headers: dict[str, str] | None = None
    payload_fn: Callable[[dict], dict[str, Any]] | None = None
    base_url_fn: Callable[[dict], str] | None = None
    pagination: AtsPagination | None = None
    scope_payload_fn: Callable[
        [Mapping[str, Any], Mapping[str, Any]],
        dict[str, Any] | None,
    ] | None = None
    scoped_location_label: str | None = None
    http_error_status_map: frozenset[int] = field(
        default_factory=frozenset
    )


def _collect_workday_israel_facets(
    value: Any,
    target_terms: frozenset[str],
    active_parameter: str = "",
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """Collect exact-country and Israel-site IDs from nested Workday facets."""

    exact_matches: list[tuple[str, str]] = []
    site_matches: list[tuple[str, str]] = []
    if isinstance(value, list):
        for item in value:
            exact, sites = _collect_workday_israel_facets(
                item,
                target_terms,
                active_parameter,
            )
            exact_matches.extend(exact)
            site_matches.extend(sites)
        return exact_matches, site_matches
    if not isinstance(value, Mapping):
        return exact_matches, site_matches

    parameter = str(
        value.get("facetParameter") or active_parameter
    ).strip()
    descriptor = str(value.get("descriptor") or "").strip().casefold()
    facet_id = str(value.get("id") or "").strip()
    parameter_text = parameter.casefold()
    is_location_parameter = any(
        keyword in parameter_text
        for keyword in (
            "location",
            "country",
            "region",
            "state",
            "province",
            "city",
        )
    )
    if parameter and facet_id and is_location_parameter:
        match = (parameter, facet_id)
        if descriptor in {"israel", "isr"}:
            exact_matches.append(match)
        elif any(term in descriptor for term in target_terms):
            site_matches.append(match)

    nested_values = value.get("values")
    if isinstance(nested_values, list):
        exact, sites = _collect_workday_israel_facets(
            nested_values,
            target_terms,
            parameter,
        )
        exact_matches.extend(exact)
        site_matches.extend(sites)
    return exact_matches, site_matches


def _workday_israel_scope_payload(
    payload: Mapping[str, Any],
    company: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Build a tenant-specific Workday payload for its Israel facet."""

    configured_filters = company.get("location_filters", [])
    target_terms = {"israel"}
    if isinstance(configured_filters, list):
        target_terms.update(
            value.strip().casefold()
            for value in configured_filters
            if isinstance(value, str) and value.strip()
        )
    exact_matches, site_matches = _collect_workday_israel_facets(
        payload.get("facets", []),
        frozenset(target_terms),
    )
    matches = exact_matches or site_matches
    if not matches:
        return None

    matches_by_parameter: dict[str, list[str]] = {}
    for parameter, facet_id in matches:
        ids = matches_by_parameter.setdefault(parameter, [])
        if facet_id not in ids:
            ids.append(facet_id)

    def parameter_priority(item: tuple[str, list[str]]) -> tuple[int, int]:
        """Prefer country-level facets, then broad multi-site coverage."""

        parameter, facet_ids = item
        normalized_parameter = parameter.casefold()
        if "country" in normalized_parameter:
            rank = 0
        elif "hierarchy1" in normalized_parameter:
            rank = 1
        else:
            rank = 2
        return rank, -len(facet_ids)

    parameter, facet_ids = min(
        matches_by_parameter.items(),
        key=parameter_priority,
    )
    return {
        "appliedFacets": {parameter: facet_ids},
        "searchText": "",
    }


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
    "lever": AtsMapping(
        envelope_key=None,
        id_fn=lambda job: job.get("id", ""),
        title_fn=lambda job: job.get("text", ""),
        location_fn=lambda job: (
            (job.get("categories") or {}).get("location", "")
        ),
        url_fn=lambda job, _base_url: job.get("hostedUrl", ""),
        content_fields_fn=lambda job: (
            job.get("descriptionPlain"),
            job.get("description"),
            job.get("additionalPlain"),
            job.get("additional"),
            job.get("lists"),
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
            "appliedFacets": {},
            "searchText": "Israel",
        },
        base_url_fn=lambda company: str(
            company.get("api_url", "")
        ).split("/wday/cxs")[0],
        pagination=AtsPagination(
            page_size=20,
            total_fn=lambda payload: payload.get("total"),
        ),
        scope_payload_fn=_workday_israel_scope_payload,
        scoped_location_label="Israel",
        http_error_status_map=frozenset({401, 403, 422}),
    ),
}
ATS_FIELD_MAP["greenhouse_eu"] = ATS_FIELD_MAP["greenhouse"]
