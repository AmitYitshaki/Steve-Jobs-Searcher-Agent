"""One-off research helper: fetch each candidate's careers page and look for
a known ATS signature in the raw HTML. Not part of the shipped application;
never imported by src/. Output is a findings file for human review before
anything is added to config/companies.json.
"""
from __future__ import annotations

import json
import re
import sys
import time
from urllib.parse import urlsplit

import requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
}
TIMEOUT_SECONDS = 15

# (ats_name, [signature substrings to search for, case-insensitive])
SIGNATURES: list[tuple[str, list[str]]] = [
    # "comeet-groups-list"/"comeet-g-r" deliberately excluded: verified false
    # positives on live sites (WEKA, HiBob, Medison, Skai, Lightrun) where
    # those CSS classnames were leftover/coincidental with zero functioning
    # Comeet integration -- no comeetvar, comeet_token, or comeet.co/.com
    # reference anywhere on the page. Require a marker Comeet itself emits.
    ("comeet", [
        "comeet.co/careers-api", "comeet-jsapi", "comeet.init",
        "comeetvar", "comeet_token", "comeet-wp-plugin",
    ]),
    ("greenhouse", ["boards.greenhouse.io", "job-boards.greenhouse.io", "greenhouse.io/embed", "grnhse_iframe"]),
    ("lever", ["jobs.lever.co", "lever-jobs-embed"]),
    ("ashby", ["jobs.ashbyhq.com", "ashby_embed", "ashbyhq.com/embed"]),
    ("workable", ["apply.workable.com", "workable-embed"]),
    ("smartrecruiters", ["careers.smartrecruiters.com", "smartrecruiters.com/embed"]),
    ("teamtailor", ["teamtailor.com"]),
    ("eightfold", ["eightfold.ai"]),
    ("workday", ["myworkdayjobs.com"]),
    ("oracle_recruiting_cloud", ["oraclecloud.com", "/hcmUI/CandidateExperience"]),
    ("icims", ["icims.com"]),
    ("taleo", ["taleo.net"]),
    ("jobvite", ["jobs.jobvite.com"]),
    ("bamboohr", ["bamboohr.com"]),
    ("phenom", ["phenompeople.com", "cdn.phenompro.com"]),
    ("successfactors", ["successfactors.com", "career.sap.com"]),
]

URL_HOST_ATS: list[tuple[str, str]] = [
    ("comeet", "comeet.com"),
    ("greenhouse", "greenhouse.io"),
    ("lever", "lever.co"),
    ("ashby", "ashbyhq.com"),
    ("workable", "workable.com"),
    ("smartrecruiters", "smartrecruiters.com"),
    ("teamtailor", "teamtailor.com"),
    ("eightfold", "eightfold.ai"),
    ("workday", "myworkdayjobs.com"),
    ("oracle_recruiting_cloud", "oraclecloud.com"),
    ("icims", "icims.com"),
    ("taleo", "taleo.net"),
    ("jobvite", "jobvite.com"),
]


def detect_from_url(url: str) -> str | None:
    """Return the ATS directly evident from the URL's host, if any."""

    host = urlsplit(url).netloc.casefold()
    for ats, fragment in URL_HOST_ATS:
        if fragment in host:
            return ats
    return None


def detect_from_body(body: str) -> tuple[str | None, str | None]:
    """Return (ats, matched signature) found in raw page HTML, if any."""

    lowered = body.casefold()
    for ats, signatures in SIGNATURES:
        for signature in signatures:
            if signature.casefold() in lowered:
                return ats, signature
    return None, None


def process(entry: dict) -> dict:
    """Fetch one candidate's careers page and classify its ATS."""

    name = entry["company_name"]
    url = entry.get("careers_url")
    result = {
        "company_name": name,
        "careers_url": url,
        "detected_ats": None,
        "evidence": None,
        "http_status": None,
        "error": None,
    }

    if not url:
        result["error"] = "no careers_url"
        return result

    url_ats = detect_from_url(url)
    if url_ats:
        result["detected_ats"] = url_ats
        result["evidence"] = f"url host matches {url_ats}"
        return result

    try:
        response = requests.get(
            url, headers=HEADERS, timeout=TIMEOUT_SECONDS, allow_redirects=True
        )
        result["http_status"] = response.status_code
        final_ats = detect_from_url(response.url)
        if final_ats:
            result["detected_ats"] = final_ats
            result["evidence"] = f"redirected to {final_ats} host"
            return result
        ats, signature = detect_from_body(response.text)
        if ats:
            result["detected_ats"] = ats
            result["evidence"] = f"page source contains {signature!r}"
        else:
            result["detected_ats"] = "custom"
            result["evidence"] = (
                f"no known ATS signature found "
                f"({len(response.text)} bytes fetched)"
            )
    except requests.RequestException as error:
        result["error"] = f"{type(error).__name__}: {error}"

    return result


def main(batch_path: str, out_path: str) -> None:
    candidates = json.load(open(batch_path, encoding="utf-8"))
    findings = []
    for i, entry in enumerate(candidates, start=1):
        result = process(entry)
        findings.append(result)
        status = result["detected_ats"] or f"ERROR: {result['error']}"
        print(f"[{i}/{len(candidates)}] {entry['company_name']:35s} -> {status}", file=sys.stderr)
        time.sleep(0.3)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(findings, f, ensure_ascii=False, indent=2)
    print(f"\nWrote {len(findings)} findings to {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
