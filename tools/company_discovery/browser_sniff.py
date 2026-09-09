"""One-off research helper: load a careers page in a real headless browser
and capture network responses that look like a jobs API or a known ATS
board, for companies static-HTML fetching could not classify. Not part of
the shipped application; never imported by src/.
"""
from __future__ import annotations

import json
import sys
from urllib.parse import urlsplit

from playwright.sync_api import Response, sync_playwright

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36"
)
NAV_TIMEOUT_MS = 25_000
SETTLE_MS = 3_000

KNOWN_ATS_HOSTS = [
    ("comeet", "comeet.com"),
    ("comeet", "comeet.co"),
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
    ("phenom", "phenompeople.com"),
    ("phenom", "phenompro.com"),
]
JOB_KEYWORDS = ("job", "career", "position", "vacanc", "requisition")


def classify_host(url: str) -> str | None:
    host = urlsplit(url).netloc.casefold()
    for ats, fragment in KNOWN_ATS_HOSTS:
        if fragment in host:
            return ats
    return None


def sniff_one(playwright, name: str, url: str) -> dict:
    result = {
        "company_name": name,
        "careers_url": url,
        "detected_ats": None,
        "evidence": None,
        "candidate_endpoints": [],
        "error": None,
    }
    browser = None
    try:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(user_agent=USER_AGENT)
        page = context.new_page()
        seen: set[str] = set()
        candidates: list[str] = []

        def on_response(response: Response) -> None:
            try:
                resp_url = response.url
                resource_type = response.request.resource_type
                content_type = response.headers.get("content-type", "")
                ats = classify_host(resp_url)
                path_q = urlsplit(resp_url).path.casefold()
                is_job_like = (
                    resource_type in ("xhr", "fetch")
                    and ("json" in content_type.casefold()
                         or any(k in path_q for k in JOB_KEYWORDS))
                )
                if (ats or is_job_like) and resp_url not in seen:
                    seen.add(resp_url)
                    candidates.append(resp_url)
            except Exception:
                pass

        page.on("response", on_response)
        page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
        page.wait_for_timeout(SETTLE_MS)

        result["candidate_endpoints"] = candidates[:15]
        for endpoint in candidates:
            ats = classify_host(endpoint)
            if ats:
                result["detected_ats"] = ats
                result["evidence"] = f"network request to {endpoint}"
                break
        if result["detected_ats"] is None:
            final_ats = classify_host(page.url)
            if final_ats:
                result["detected_ats"] = final_ats
                result["evidence"] = f"page navigated to {page.url}"
        if result["detected_ats"] is None:
            result["detected_ats"] = "custom"
            result["evidence"] = (
                f"no known ATS host in {len(candidates)} captured "
                "job-like network responses"
            )
    except Exception as error:
        result["error"] = f"{type(error).__name__}: {error}"
    finally:
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass
    return result


def main(batch_path: str, out_path: str) -> None:
    candidates = json.load(open(batch_path, encoding="utf-8"))
    findings = []
    with sync_playwright() as playwright:
        for i, entry in enumerate(candidates, start=1):
            result = sniff_one(playwright, entry["company_name"], entry["careers_url"])
            findings.append(result)
            status = result["detected_ats"] or f"ERROR: {result['error']}"
            print(f"[{i}/{len(candidates)}] {entry['company_name']:30s} -> {status}", file=sys.stderr)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(findings, f, ensure_ascii=False, indent=2)
    print(f"\nWrote {len(findings)} findings to {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
