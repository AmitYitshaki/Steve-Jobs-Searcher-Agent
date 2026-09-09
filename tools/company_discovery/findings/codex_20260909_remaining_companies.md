# Endpoint research for the remaining 117 companies

Research completed on 2026-09-09 against first-party careers pages and public recruitment APIs. The companion CSV has exactly one row for every requested company and the required columns: `company_name,status,ats_type,api_url,job_selector,verification`.

## Results

| Status | Companies |
|---|---:|
| Solved | 45 |
| Blocked | 28 |
| Unresolved | 44 |
| Total | 117 |

`solved` requires actual fetched job records and includes an observed count plus real titles. An `api_url` is present only when that URL returned records during this run. HTML sources instead use `job_selector`. Verified-empty endpoints remain blank and unresolved. `blocked` records a concrete WAF, HTTP error, or failed public response; it does not claim that an integration is impossible.

## Integration implications

Many of the recovered sources are evidence for implementation rather than drop-in configuration:

- The 18 solved Comeet sources generally return JSON arrays that the current HTML-oriented Comeet adapter cannot parse. Tufin's first-party proxy returns an object whose `raw` array must be used to avoid grouped duplicates.
- Cross River's verified Comeet feed covers Israel; its US vacancies use a separate Greenhouse integration.
- eBay and Snowflake expose structured Phenom job data in first-party HTML, but the existing generic API mapping does not consume that envelope.
- Microchip's Workday result set uses identifier fields that the current mapping does not recognize.
- D-ID and AccessFintech require a Workable v3 POST with the documented request body.
- Several custom selectors carry a warning in the CSV where one final browser-level extractor check is still prudent.

## Detailed evidence

- [Comeet candidates](codex_20260909_group_a.md): 29 companies, 18 solved.
- [Known ATS candidates](codex_20260909_group_b.md): 13 companies, 8 solved.
- [Custom career pages](codex_20260909_group_c.md): 63 companies, 14 solved.
- [Unsupported and newly discovered sources](codex_20260909_group_de.md): 12 companies, 5 solved.

Each report links the relevant official source and records request method, response shape, sample titles and material coverage limits. Supporting JSON evidence is kept next to the reports. Production code, `config/companies.json`, runtime data, AI calls and Telegram were not touched.

## Research limit

Automatic approval review rejected the last network/parser passes after the account reached its tool-usage limit. No workaround was attempted. The already captured first-party responses were enough to complete all 117 rows; affected companies were conservatively left blocked or unresolved rather than promoted from a lead alone.
