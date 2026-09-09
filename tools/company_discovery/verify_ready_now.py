"""One-off research helper: derive and verify a real API endpoint for each
"ready now" candidate (an ATS this project already has an adapter for), by
extracting the company's own token/tenant from its page and requesting the
real endpoint directly -- never guessing a URL without confirming it first.

Not part of the shipped application; never imported by src/.
"""
from __future__ import annotations

import json
import re
import sys

import requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
TIMEOUT = 15

GH_HOST_PATTERN = re.compile(r"(?:job-boards|boards)\.greenhouse\.io/([a-zA-Z0-9_-]+)")
LEVER_HOST_PATTERN = re.compile(r"jobs\.lever\.co/([a-zA-Z0-9_-]+)")
ASHBY_HOST_PATTERN = re.compile(r"jobs\.ashbyhq\.com/([a-zA-Z0-9_-]+)")
SMARTRECRUITERS_HOST_PATTERN = re.compile(r"careers\.smartrecruiters\.com/([a-zA-Z0-9_.-]+)")
WORKDAY_HOST_PATTERN = re.compile(
    r"([a-z0-9-]+)\.(wd\d)\.myworkday(?:jobs|site)\.com/"
    r"(?:[a-zA-Z-]+/recruiting/[a-zA-Z0-9_-]+/)?([A-Za-z0-9_-]+)"
)
EIGHTFOLD_HOST_PATTERN = re.compile(r"([a-z0-9.-]+)\.eightfold\.ai")


def _fetch(url: str) -> str | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        return resp.text
    except requests.RequestException:
        return None


def _find_token(careers_url: str, pattern: re.Pattern, fetch_if_missing: bool = True) -> str | None:
    match = pattern.search(careers_url)
    if match:
        return match.group(1)
    if not fetch_if_missing:
        return None
    html = _fetch(careers_url)
    if html is None:
        return None
    match = pattern.search(html)
    return match.group(1) if match else None


def verify_greenhouse(careers_url: str) -> dict:
    token = _find_token(careers_url, GH_HOST_PATTERN)
    if not token:
        return {"status": "no_token_found"}
    api_url = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"
    try:
        resp = requests.get(api_url, headers=HEADERS, timeout=TIMEOUT)
    except requests.RequestException as e:
        return {"status": "request_error", "detail": str(e), "api_url": api_url}
    if resp.status_code != 200:
        return {"status": f"http_{resp.status_code}", "api_url": api_url}
    try:
        data = resp.json()
    except ValueError:
        return {"status": "invalid_json", "api_url": api_url}
    jobs = data.get("jobs") if isinstance(data, dict) else None
    if not isinstance(jobs, list):
        return {"status": "no_jobs_field", "api_url": api_url}
    return {"status": "verified", "api_url": api_url, "job_count": len(jobs)}


def verify_lever(careers_url: str) -> dict:
    token = _find_token(careers_url, LEVER_HOST_PATTERN)
    if not token:
        return {"status": "no_token_found"}
    for region_host in ("api.lever.co", "api.eu.lever.co"):
        api_url = f"https://{region_host}/v0/postings/{token}?mode=json"
        try:
            resp = requests.get(api_url, headers=HEADERS, timeout=TIMEOUT)
        except requests.RequestException:
            continue
        if resp.status_code == 200:
            try:
                data = resp.json()
            except ValueError:
                continue
            if isinstance(data, list):
                return {"status": "verified", "api_url": api_url, "job_count": len(data)}
    return {"status": "no_region_worked", "token": token}


def verify_ashby(careers_url: str) -> dict:
    token = _find_token(careers_url, ASHBY_HOST_PATTERN)
    if not token:
        return {"status": "no_token_found"}
    api_url = f"https://api.ashbyhq.com/posting-api/job-board/{token}"
    try:
        resp = requests.get(api_url, headers=HEADERS, timeout=TIMEOUT)
    except requests.RequestException as e:
        return {"status": "request_error", "detail": str(e), "api_url": api_url}
    if resp.status_code != 200:
        return {"status": f"http_{resp.status_code}", "api_url": api_url}
    try:
        data = resp.json()
    except ValueError:
        return {"status": "invalid_json", "api_url": api_url}
    jobs = data.get("jobs") if isinstance(data, dict) else None
    if not isinstance(jobs, list):
        return {"status": "no_jobs_field", "api_url": api_url}
    return {"status": "verified", "api_url": api_url, "job_count": len(jobs)}


def verify_smartrecruiters(careers_url: str) -> dict:
    token = _find_token(careers_url, SMARTRECRUITERS_HOST_PATTERN)
    if not token:
        return {"status": "no_token_found"}
    api_url = f"https://api.smartrecruiters.com/v1/companies/{token}/postings"
    try:
        resp = requests.get(api_url, headers=HEADERS, timeout=TIMEOUT)
    except requests.RequestException as e:
        return {"status": "request_error", "detail": str(e), "api_url": api_url}
    if resp.status_code != 200:
        return {"status": f"http_{resp.status_code}", "api_url": api_url}
    try:
        data = resp.json()
    except ValueError:
        return {"status": "invalid_json", "api_url": api_url}
    content = data.get("content") if isinstance(data, dict) else None
    if not isinstance(content, list):
        return {"status": "no_content_field", "api_url": api_url}
    return {"status": "verified", "api_url": api_url, "job_count": len(content)}


def verify_workday(careers_url: str) -> dict:
    html = _fetch(careers_url)
    haystack = careers_url + "\n" + (html or "")
    match = WORKDAY_HOST_PATTERN.search(haystack)
    if not match:
        return {"status": "no_token_found"}
    tenant, wd, site = match.group(1), match.group(2), match.group(3)
    api_url = f"https://{tenant}.{wd}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"
    payload = {"limit": 20, "appliedFacets": {}, "searchText": "Israel"}
    try:
        resp = requests.post(
            api_url,
            json=payload,
            headers={**HEADERS, "Accept": "application/json", "Content-Type": "application/json"},
            timeout=TIMEOUT,
        )
    except requests.RequestException as e:
        return {"status": "request_error", "detail": str(e), "api_url": api_url}
    if resp.status_code != 200:
        return {"status": f"http_{resp.status_code}", "api_url": api_url}
    try:
        data = resp.json()
    except ValueError:
        return {"status": "invalid_json", "api_url": api_url}
    postings = data.get("jobPostings") if isinstance(data, dict) else None
    if not isinstance(postings, list):
        return {"status": "no_jobPostings_field", "api_url": api_url}
    return {
        "status": "verified",
        "api_url": api_url,
        "job_count": len(postings),
        "total": data.get("total"),
    }


def verify_eightfold(careers_url: str) -> dict:
    html = _fetch(careers_url)
    haystack = careers_url + "\n" + (html or "")
    hosts = [h for h in set(EIGHTFOLD_HOST_PATTERN.findall(haystack)) if h != "app"]
    if not hosts:
        return {"status": "no_dedicated_host_found"}
    host = sorted(hosts, key=len)[0]
    api_url = f"https://{host}.eightfold.ai/api/apply/v2/jobs"
    try:
        resp = requests.get(
            api_url, headers={**HEADERS, "Accept": "application/json"}, timeout=TIMEOUT
        )
    except requests.RequestException as e:
        return {"status": "request_error", "detail": str(e), "api_url": api_url}
    if resp.status_code != 200:
        return {
            "status": f"http_{resp.status_code}",
            "api_url": api_url,
            "careers_url": f"https://{host}.eightfold.ai/careers",
        }
    try:
        resp.json()
    except ValueError:
        return {"status": "invalid_json", "api_url": api_url}
    return {
        "status": "verified",
        "api_url": f"https://{host}.eightfold.ai/careers",
        "job_count": "n/a (see adapter)",
    }


VERIFIERS = {
    "greenhouse": verify_greenhouse,
    "lever": verify_lever,
    "ashby": verify_ashby,
    "smartrecruiters": verify_smartrecruiters,
    "workday": verify_workday,
    "eightfold": verify_eightfold,
}


def main(in_path: str, out_path: str) -> None:
    data = json.load(open(in_path, encoding="utf-8"))
    supported = set(VERIFIERS)
    candidates = [r for r in data if r["detected_ats"] in supported]
    results = []
    for i, r in enumerate(candidates, start=1):
        verifier = VERIFIERS[r["detected_ats"]]
        outcome = verifier(r["careers_url"])
        results.append(
            {
                "company_name": r["company_name"],
                "ats_type": r["detected_ats"],
                "careers_url": r["careers_url"],
                **outcome,
            }
        )
        print(
            f"[{i}/{len(candidates)}] {r['company_name']:28s} "
            f"({r['detected_ats']:16s}) -> {outcome['status']}",
            file=sys.stderr,
        )
    json.dump(results, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\nWrote {len(results)} results to {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
