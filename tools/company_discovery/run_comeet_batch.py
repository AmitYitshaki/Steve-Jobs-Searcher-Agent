"""One-off research helper: run the real production scrape_comeet adapter
against every discovered Comeet candidate and record how many jobs each
returns. Not part of the shipped application; never imported by src/.
"""
from __future__ import annotations

import json
import re
import sys

sys.path.insert(0, "src")
from scrapers.browser.custom_adapters import scrape_comeet


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")
    return slug or "company"


def main(in_path: str, out_path: str) -> None:
    candidates = json.load(open(in_path, encoding="utf-8"))
    results = []
    for i, entry in enumerate(candidates, start=1):
        company_id = _slugify(entry["company_name"])
        try:
            jobs = scrape_comeet({"company_id": company_id, "api_url": entry["api_url"]})
            count = len(jobs)
            sample = jobs[0]["title"] if jobs else ""
        except Exception as error:  # noqa: BLE001 - research script, log and continue
            count = -1
            sample = f"ERROR: {type(error).__name__}: {error}"
        results.append(
            {
                "company_name": entry["company_name"],
                "api_url": entry["api_url"],
                "job_count": count,
                "sample_title": sample,
            }
        )
        print(
            f"[{i}/{len(candidates)}] {entry['company_name']:28s} -> {count} jobs",
            file=sys.stderr,
        )
    json.dump(results, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\nWrote {len(results)} results to {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
