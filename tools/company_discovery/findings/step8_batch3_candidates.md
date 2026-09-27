# Step 8 batch 3 candidate findings

Date: 2026-09-26

## Outcome

This batch activates 25 companies. Every activated company passed all four
gates against live first-party ATS data:

1. a real employer careers surface;
2. an ATS identity confirmed from the employer/ATS surface;
3. at least one job accepted by the production strict Israel location filter;
4. at least one current title accepted by `matches_target_role()`.

All 25 `company_id` and `api_url` values are new relative to the 329-entry
catalog at `c713132`. The only duplicate API URL in the resulting catalog is
the pre-existing Mastercard/Dynamic Yield Workday tenant already documented
after batch 2; none of the batch-3 additions reuse an existing URL.

The requested 40-50 target was deliberately not padded. Search-index results
were treated only as discovery leads; activation counts below come from live
production-adapter responses.

## Activated

Counts are `all jobs / strict-Israel jobs / strict-Israel target-role jobs`.

| Company (`company_id`) | ATS and primary evidence | Live counts | Example qualifying title |
|---|---|---:|---|
| Ledge (`ledge`) | [Ashby board](https://jobs.ashbyhq.com/ledge) / [API](https://api.ashbyhq.com/posting-api/job-board/ledge) | 4 / 2 / 2 | AI Engineer |
| Tavily (`tavily`) | [Official Ashby posting](https://jobs.ashbyhq.com/tavily/58948731-c993-4127-a723-a96b1dcd841c) / [API](https://api.ashbyhq.com/posting-api/job-board/tavily) | 18 / 9 / 7 | Software Engineer - Web Crawling |
| PointFive (`pointfive`) | [Official Ashby posting](https://jobs.ashbyhq.com/pointfive/d421e4e5-85cd-4ebb-a480-442e83057c6f/) / [API](https://api.ashbyhq.com/posting-api/job-board/pointfive) | 11 / 7 / 3 | Senior Software Engineer - Endpoint |
| Enclave AI (`enclave_ai`) | [Official Ashby posting](https://jobs.ashbyhq.com/enclave/533fbd6a-724f-4a08-b1fe-e82701718d7b) / [API](https://api.ashbyhq.com/posting-api/job-board/enclave) | 5 / 2 / 2 | Senior Software Engineer |
| Glow (`glow`) | [Official Ashby posting](https://jobs.ashbyhq.com/glow/890cadf7-46ca-437a-88c8-7636561961d2) / [API](https://api.ashbyhq.com/posting-api/job-board/glow) | 16 / 10 / 7 | Vulnerability Researcher |
| Vivid (`vivid`) | [Ashby board](https://jobs.ashbyhq.com/vivid) / [API](https://api.ashbyhq.com/posting-api/job-board/vivid) | 2 / 2 / 1 | Senior Software Engineer |
| Sweep (`sweep`) | [Official Ashby posting](https://jobs.ashbyhq.com/sweep/18f9dc28-9593-41cd-9ed1-ca12a36e0c98) / [API](https://api.ashbyhq.com/posting-api/job-board/sweep) | 7 / 2 / 1 | Senior Back-End Developer |
| Pi Security (`pi_security`) | [Official Ashby posting](https://jobs.ashbyhq.com/pi-security/a3203d1b-93fe-4898-8808-86863fc11586) / [API](https://api.ashbyhq.com/posting-api/job-board/pi-security) | 9 / 2 / 2 | Security Researcher |
| Zafran Security (`zafran_security`) | [Official Ashby posting](https://jobs.ashbyhq.com/zafran-security/246ae954-d395-45ab-82c9-28b15d1fb6c4/) / [API](https://api.ashbyhq.com/posting-api/job-board/zafran-security) | 29 / 9 / 3 | Backend Developer |
| Irregular (`irregular`) | [Ashby board](https://jobs.ashbyhq.com/irregular) / [API](https://api.ashbyhq.com/posting-api/job-board/irregular) | 9 / 9 / 4 | Research Engineer |
| HUMAN (`human_security`) | [Official Ashby posting](https://jobs.ashbyhq.com/HUMAN/e1c3cfb8-d78f-4569-ab0e-80ed52dda98b/) / [API](https://api.ashbyhq.com/posting-api/job-board/HUMAN) | 6 / 2 / 2 | Backend Engineer |
| Reindeer AI (`reindeer_ai`) | [Ashby board](https://jobs.ashbyhq.com/reindeer-ai) / [API](https://api.ashbyhq.com/posting-api/job-board/reindeer-ai) | 14 / 6 / 3 | AI Engineer |
| Lumana (`lumana`) | [Official Ashby posting](https://jobs.ashbyhq.com/lumana/75f73732-1a74-40a9-9bc6-004de793f3f8) / [API](https://api.ashbyhq.com/posting-api/job-board/lumana) | 11 / 4 / 2 | Senior Software Engineer - Edge |
| Echo.ai (`echo_ai`) | [Official careers page](https://www.echo.ai/careers) / [Ashby API](https://api.ashbyhq.com/posting-api/job-board/echo.ai) | 13 / 11 / 6 | Software Engineer |
| Shapes (`shapes`) | [Official Ashby posting](https://jobs.ashbyhq.com/shapes/413e974a-a0e3-4cfb-a253-e1f32931c4e0) / [API](https://api.ashbyhq.com/posting-api/job-board/shapes) | 6 / 6 / 2 | Software Engineer |
| Act Security (`act_security`) | [Official Ashby posting](https://jobs.ashbyhq.com/act/e27cb891-b723-4401-99e4-2fd80618f2f8) / [API](https://api.ashbyhq.com/posting-api/job-board/act-security) | 4 / 4 / 2 | Software Engineer (Data Platform) |
| Matia (`matia`) | [Official Ashby posting](https://jobs.ashbyhq.com/matia/d39b11fc-1c44-4593-bc50-2385b4c581a2) / [API](https://api.ashbyhq.com/posting-api/job-board/matia) | 13 / 6 / 4 | Senior Software Engineer |
| MyHeritage (`myheritage`) | [Greenhouse board](https://job-boards.greenhouse.io/myheritage) / [API](https://boards-api.greenhouse.io/v1/boards/myheritage/jobs?content=true) | 6 / 5 / 2 | Senior Machine Learning Engineer |
| ORION Security (`orion_security`) | [Greenhouse board](https://job-boards.greenhouse.io/orioncscybersecurityltd) / [API](https://boards-api.greenhouse.io/v1/boards/orioncscybersecurityltd/jobs?content=true) | 7 / 3 / 1 | Software Engineer |
| Navan (`navan`) | [Greenhouse board](https://job-boards.greenhouse.io/tripactions) / [API](https://boards-api.greenhouse.io/v1/boards/tripactions/jobs?content=true) | 212 / 9 / 3 | Senior Front End Software Engineer |
| Speechify (`speechify`) | [Official Greenhouse posting](https://job-boards.greenhouse.io/speechify/jobs/5975237004) / [API](https://boards-api.greenhouse.io/v1/boards/speechify/jobs?content=true) | 254 / 3 / 3 | Software Engineer, Platform - Haifa, Israel |
| Venn (`venn`) | [Greenhouse board](https://job-boards.greenhouse.io/venncity) / [API](https://boards-api.greenhouse.io/v1/boards/venncity/jobs?content=true) | 9 / 2 / 2 | Data Lead- Full-Stack Data Engineer |
| Palantir (`palantir`) | [Lever board](https://jobs.lever.co/palantir) / [API](https://api.lever.co/v0/postings/palantir?mode=json) | 321 / 2 / 1 | Forward Deployed Software Engineer |
| Nexar (`nexar`) | [SmartRecruiters board](https://jobs.smartrecruiters.com/NexarInc) / [API](https://api.smartrecruiters.com/v1/companies/NexarInc/postings) | 2 / 2 / 2 | Junior Software Engineer |
| NielsenIQ (`nielseniq`) | [Official SmartRecruiters posting](https://jobs.smartrecruiters.com/NielsenIQ/744000139165539-senior-data-engineer) / [API](https://api.smartrecruiters.com/v1/companies/NielsenIQ/postings) | 392 / 3 / 2 | Software Engineer (Mid) - Backend AI Engineer |

ATS breakdown: 17 Ashby, 5 Greenhouse, 1 Lever, and 2 SmartRecruiters.

## Held: no production-recognized Israel job

These boards were live and returned jobs, but zero current records passed the
strict production location filter. Search snippets were not accepted as
activation evidence.

| Company | Primary ATS evidence | Live result | Disposition |
|---|---|---:|---|
| Confluent | [Ashby API](https://api.ashbyhq.com/posting-api/job-board/confluent) | 20 / 0 Israel | Hold: no Israel job. |
| DigitalOcean | [Greenhouse API](https://boards-api.greenhouse.io/v1/boards/digitalocean98/jobs?content=true) | 164 / 0 | Hold. |
| JetBrains | [Greenhouse API](https://boards-api.greenhouse.io/v1/boards/jetbrains/jobs?content=true) | 65 / 0 | Hold. |
| Nintex | [Greenhouse API](https://boards-api.greenhouse.io/v1/boards/nintex/jobs?content=true) | 14 / 0 | Hold. |
| Sequence | [Ashby API](https://api.ashbyhq.com/posting-api/job-board/sequence) | 11 / 0 | Hold. |
| CloudZero | [Ashby API](https://api.ashbyhq.com/posting-api/job-board/cloudzero) | 16 / 0 | Hold. |
| Canditech | [Lever API](https://api.lever.co/v0/postings/canditech?mode=json) | 1 / 0 | Hold. |
| Aeva | [Lever API](https://api.lever.co/v0/postings/aeva?mode=json) | 44 / 0 | Hold. |
| Zynga | [Greenhouse API](https://boards-api.greenhouse.io/v1/boards/zyngacareers/jobs?content=true) | 44 / 0 | Hold; indexed Israel result was stale. |
| Ping Identity | [Greenhouse API](https://boards-api.greenhouse.io/v1/boards/pingidentity/jobs?content=true) | 77 / 0 | Hold; indexed Israel result was stale. |
| Vonage | [Greenhouse API](https://boards-api.greenhouse.io/v1/boards/vonage/jobs?content=true) | 22 / 0 | Hold; indexed Israel result was stale. |

Twingate is held separately: its two-job [Lever feed](https://api.lever.co/v0/postings/twingate?mode=json)
contains `Remote (US or Israel)`. The production filter rejects the record
because it contains a blocked US signal before the Israel signal. This batch
does not alter filter semantics; the candidate is therefore not activated.

## Held: no target-role job

These companies had at least one current strict-Israel job, but no current
Israel title passed the repository's actual relevance gate.

| Company | Primary ATS evidence | Live result | Disposition |
|---|---|---:|---|
| Wonderful | [Ashby API](https://api.ashbyhq.com/posting-api/job-board/wonderful) | 123 / 7 Israel / 0 target | Hold: no target-role job. |
| Snappy | [Ashby API](https://api.ashbyhq.com/posting-api/job-board/Snappy) | 4 / 1 / 0 | Hold. |
| Chamelio | [Ashby API](https://api.ashbyhq.com/posting-api/job-board/chamelio) | 10 / 3 / 0 | Hold. |
| Jiga | [Ashby API](https://api.ashbyhq.com/posting-api/job-board/jiga) | 12 / 1 / 0 | Hold. |
| Triple Whale | [Greenhouse API](https://boards-api.greenhouse.io/v1/boards/triplewhale/jobs?content=true) | 9 / 1 / 0 | Hold. |
| Sauce | [Lever API](https://api.lever.co/v0/postings/Sauce?mode=json) | 14 / 1 / 0 | Hold. |
| Nebari | [Ashby board](https://jobs.ashbyhq.com/nebari) | One general `Open Job Titles` posting | Hold; no qualifying current title. |

## Held: zero jobs or identity/source issue

| Candidate | Evidence | Disposition |
|---|---|---|
| DoubleVerify | [Greenhouse API](https://boards-api.greenhouse.io/v1/boards/doubleverify/jobs?content=true) returned no jobs | Hold: zero live jobs; search index was stale. |
| Deel, Verint, Lumen | Public board-token probes returned empty boards | Hold: zero live jobs. |
| MyTeam | [Workable posting](https://apply.workable.com/myteam/j/E41B6C9D15/) | Excluded: staffing/recruiting intermediary, not the employing company. |
| Bjak / A1 | [Ashby board](https://jobs.ashbyhq.com/bjakcareer) | Previously documented employer/product identity ambiguity; not reactivated. |
| Echo legacy Comeet surface | Previously found Comeet tenant `echo/9A.006` | Not activated. The current [echo.ai careers page](https://www.echo.ai/careers) establishes Ashby as the canonical source for the activated cybersecurity employer. |

## Duplicate and already-covered discoveries

Discovery searches also surfaced existing catalog companies including Hello
Heart, Redis, monday.com, Viz.ai, Pagaya, At-Bay, DoiT, Forter, Next Insurance,
Pendo, Moon Active, SafeBreach, ControlUp, Unframe, Tenable, Aidoc, Guardz,
Bluevine, Check Point, ServiceNow, Apiiro, and Wolt. They were discarded before
activation research. No new unsupported ATS family was encountered in this
batch, and no new company needs a canonical-feed decision after the Echo.ai
and Tavily checks above.

## Verification notes

- All live counts were produced through `fetch_jobs_from_company()` and the
  same `LocationFilter(strict_mode=True)` and `matches_target_role()` functions
  used by discovery/production code.
- Every successful result had unique normalized job IDs and non-empty titles.
- No location alias or adapter change was needed for this batch. NielsenIQ's
  `Yokneam Illit` records are already covered safely by the existing
  `Yokneam` location phrase.
