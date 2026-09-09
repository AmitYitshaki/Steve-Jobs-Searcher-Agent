# Group C research: 63 custom companies

Research-only results captured on 2026-09-09. Every solved row is based on job records fetched from the company's official careers page. The companion CSV contains all 63 requested companies, exact status, a candidate selector, observed count and sample titles.

## Outcome

- Solved: 14
- Blocked by a concrete access or response failure: 22
- Unresolved after bounded inspection: 27

The strongest immediately usable HTML sources are [DriveNets](https://drivenets.com/careers/), [Datarails](https://www.datarails.com/careers/), [Valens](https://www.valens.com/positions/), [WalkMe](https://www.walkme.com/careers/careers_list/), [Noma Security](https://noma.security/careers), [Komodor](https://komodor.com/careers/), [Sunbit](https://sunbit.com/careers/), [Bright Data](https://brightdata.com/careers), and [Adnimation](https://www.adnimation.com/careers/). Pentera, TytoCare, UVision, Priority Software and Upstream also expose real HTML records, but their proposed selectors should receive one browser-level extractor check before being copied into configuration.

DriveNets returned 34 JSON-LD JobPosting objects and matching DOM rows, including AI Platform Software Engineer, ATE Software Engineer and Junior Hardware Engineer. Datarails returned 11 title-bearing cards. WalkMe returned 29 direct job URLs rather than department-only controls. Noma returned 24 distinct position URLs. Bright Data returned 43 distinct job paths after removing repeated responsive links. Komodor had only one current role, which is explicitly recorded rather than padded with non-job content.

## Deliberately unpromoted leads

SolarEdge's known Comeet `71.00A` lead was not promoted because its response records were not fetched. Nexxen's genuine Greenhouse embed was not promoted because its public board API had returned 404. Fundbox and Credo exposed HiBob apply links but the verified markup did not establish a complete, title-bearing selector compatible with the current extractor. Radware and IDE exposed JavaScript/Taleo interactions without fetchable record URLs. Playtika requires a complete crawl across department views. Pecan's repeated elements looked like filters, not job cards.

Blocked means this research run encountered a specific WAF, HTTP error, or failed public response. It does not mean that no integration can ever be built. Unresolved likewise means no safe endpoint or selector was verified within this bounded run.

## Evidence and limits

The source capture index is `codex_20260909_custom_discovery.json`; bounded public HTML captures are under `codex_20260909_custom_evidence/`. Requests used public first-party pages, no login or private credentials. Production code, catalogue configuration, runtime state, AI calls and Telegram were not executed or changed.

The final parser rerun was rejected by automatic approval review because the account hit its tool-usage limit. The 63-row report was therefore completed conservatively from the already saved responses. Rows affected by that interruption remain blocked or unresolved, with blank endpoints.
