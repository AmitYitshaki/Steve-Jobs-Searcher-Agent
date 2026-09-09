# Group A research: 29 Comeet candidates

Research only, 2026-09-09. Every solved URL was personally fetched and returned actual records. All requests were GET with no payload; HTTP requests used public pages and website-published recruitment widget tokens, with no account credentials. Sources and timestamps are recorded below and in the companion API evidence JSON. Existing browser_sniff.py was reused for five remaining sources, serially; HTTP concurrency was bounded at three.

CRITICAL: solved means the endpoint returns real records, not that it can be copied into current configuration. The production Comeet adapter only parses HTML and does not accept these JSON arrays. Most APIs return a root list of uid/name/location/department/job URLs. Tufin instead returns {raw, groupedByDepartment, groupedByLocation}; count only raw to avoid grouped duplicates. Add appropriate parser support before using these endpoints. Counts are observed response records, not independently audited completeness totals. No pagination indicator was observed in these arrays. One-record results cannot provide 2-3 distinct titles. Trullion's sole record is General Application, not a specific actively hiring role.

Empty API responses (Moon Active, FundGuard, Explorium) stay unresolved with blank api_url. The request is retained in API evidence only. They establish an empty response at the timestamp, not global absence of jobs. Cross River covers Israel; a separate US Greenhouse integration appears on the first-party page.

Nova and Appcharge have genuine HTML job cards, but final selector/count validation was not completed. AudioCodes mixes Apply Now fragment links and real detail links in each card, so a naive generic extractor can choose the wrong href. BioCatch and Candivore have real browser-observed Comeet endpoints; no response-record verification was completed, therefore no URL is promoted.

Limit: the final extra verification call was rejected by automatic approval review because of a tool usage limit. No workaround or further network requests were used. This report conservatively preserves unresolved outcomes. Production code/configuration, runtime data, AI and Telegram were not executed or changed.

Evidence: codex_20260909_group_a_api.json contains API responses and source-derived request URLs; codex_20260909_group_a_tufin.json and codex_20260909_group_a_crossriver.json contain the additional verified responses; codex_20260909_group_a_browser.json records browser discoveries. Raw public-page and asset captures are local research material, not sanitized artifacts for external sharing.
## Nova - unresolved

Source: https://www.novami.com/location_filter/israel/

Checked: 2026-09-09T13:42:23.983365+00:00

Real /comeetitem/ job anchors with class positionTitle observed: Accounts Receivable (AR) Bookkeeper | AI Manager | Assembly and Calibration Technician. Full selector count not completed; no verified URL emitted.

## Moon Active - unresolved

Source: https://www.moonactive.com/careers/

Checked: 2026-09-09T13:42:23.983365+00:00

HTTP 200 JSON []; verified empty response, no records to validate; api_url intentionally blank.

## Healthy.io - solved

Source: https://healthy.io/careers/

Checked: 2026-09-09T13:42:23.984361+00:00

HTTP 200; 1 records; titles: Senior Developer. JSON parser support required.

## AudioCodes - unresolved

Source: https://www.audiocodes.com/careers

Checked: 2026-09-09T13:42:24.488321+00:00

Real .accordion__head cards with h3.subtitle titles and detail links observed, including APAC - Voca CIC Presale Engineer. First anchor is Apply Now fragment; generic extractor compatibility unverified.

## Earnix - unresolved

Source: https://earnix.com/our-story/careers/israel/

Checked: 2026-09-09T13:42:24.653036+00:00

Official Israel page embedded open-position SSR hits=[]; serial browser only observed navigation JSON; empty versus failed upstream feed not established.

## NextSilicon - solved

Source: https://www.nextsilicon.com/careers/

Checked: 2026-09-09T13:42:25.287429+00:00

HTTP 200; 36 records; titles: AI Compiler Engineer | AI Libraries Engineer | Brno- Senior Compiler Engineer. JSON parser support required.

## Personetics - solved

Source: https://personetics.com/careers/

Checked: 2026-09-09T13:42:25.353171+00:00

HTTP 200; 13 records; titles: AI Customer Success Partner (North America) | Business Applications Manager | Data Architect. JSON parser support required.

## Aqua Security - solved

Source: https://www.aquasec.com/about-us/careers/

Checked: 2026-09-09T13:42:25.501928+00:00

HTTP 200; 7 records; titles: IT Support Engineer | Office & Operations Manager | Regional Sales Manager. JSON parser support required.

## BioCatch - unresolved

Source: https://www.biocatch.com/cybersecurity-careers

Checked: 2026-09-09T13:42:25.909838+00:00

Serial browser discovered a Comeet positions endpoint, but response records were not captured or verified; subsequent verification blocked by tool approval usage limit.

## Innoviz - blocked

Source: https://innoviz.tech/join-us

Checked: 2026-09-09T13:42:26.341761+00:00

HTTP 200 Imperva challenge; serial browser reached hCaptcha checksiteconfig, no job data. Local blockage, not a global availability claim.

## Atera - solved

Source: https://www.atera.com/careers/

Checked: 2026-09-09T13:42:26.456762+00:00

HTTP 200; 19 records; titles: ABM Manager | Account Executive | Controller. JSON parser support required.

## Overwolf - solved

Source: https://careers.overwolf.com/

Checked: 2026-09-09T13:42:27.338268+00:00

HTTP 200; 11 records; titles: Author Relations Manager | Content Moderator - UK | Developer Relations Manager. JSON parser support required.

## Tufin - solved

Source: https://www.tufin.com/careers

Checked: 2026-09-09T13:42:27.342719+00:00

HTTP 200; 9 raw records; titles: AI System Architect | AI System Architect - US | Associate Product Manager. Object raw array requires parser support.

## FundGuard - unresolved

Source: https://www.fundguard.com/careers

Checked: 2026-09-09T13:42:27.345719+00:00

HTTP 200 JSON []; verified empty response, no records to validate; api_url intentionally blank.

## Cross River - solved

Source: https://www.crossriver.com/careers

Checked: 2026-09-09T13:42:28.824816+00:00

HTTP 200; 16 Israel records; titles: AI Security Engineer | Dynamics 365 Senior Developer | Employer Brand & Talent Marketing. US uses separate Greenhouse board; JSON parser required.

## Candivore - unresolved

Source: https://www.candivore.com/careers

Checked: 2026-09-09T13:42:28.963584+00:00

Serial browser discovered a Comeet positions endpoint, but response records were not captured or verified; subsequent verification blocked by tool approval usage limit.

## Akeyless - solved

Source: https://www.akeyless.io/careers

Checked: 2026-09-09T13:42:29.583170+00:00

HTTP 200; 10 records; titles: AI Engineering Tech Lead | Automation Infrastructure Engineer | Customer Success Architect - US. JSON parser support required.

## EX.CO - solved

Source: https://www.ex.co/careers

Checked: 2026-09-09T13:42:29.689471+00:00

HTTP 200; 5 records; titles: Customer Success Manager- NY | Customer Success Manager- TLV | Director, Business Development. JSON parser support required.

## Alma Lasers - solved

Source: https://www.almalasers.com/careers

Checked: 2026-09-09T13:42:29.827958+00:00

HTTP 200; 36 records; titles: Area Business Director | Area Business Director - New England | Area Business Director - NYC. JSON parser support required.

## IONIX - solved

Source: https://www.ionix.io/careers

Checked: 2026-09-09T13:42:31.348039+00:00

HTTP 200; 6 records; titles: Bookkeeper and Payroll Controller | Channel Account Manager | Director of Customer Success. JSON parser support required.

## Port - solved

Source: https://www.getport.io/careers

Checked: 2026-09-09T13:42:32.308768+00:00

HTTP 200; 26 records; titles: Account Manager | Account Manager, LATAM | Agentic Engineering Evangelist. JSON parser support required.

## Trullion - solved

Source: https://www.trullion.com/careers

Checked: 2026-09-09T13:42:32.688486+00:00

HTTP 200; 1 records; titles: General Application. JSON parser support required.

## GeoEdge - solved

Source: https://www.geoedge.com/careers

Checked: 2026-09-09T13:42:33.123556+00:00

HTTP 200; 5 records; titles: Business Development Associate | Office & Employee Experience Manager - Mat Leave Cover | Product Marketing Manager. JSON parser support required.

## Minute Media - solved

Source: https://www.minutemedia.com/company/careers

Checked: 2026-09-09T13:42:33.589717+00:00

HTTP 200; 11 records; titles: Ad Ops Manager | Data Scientist | Full Stack Developer. JSON parser support required.

## Explorium - unresolved

Source: https://www.explorium.ai/careers

Checked: 2026-09-09T13:42:37.657236+00:00

HTTP 200 JSON []; verified empty response, no records to validate; api_url intentionally blank.

## Panorays - solved

Source: https://www.panorays.com/careers

Checked: 2026-09-09T13:42:37.851305+00:00

HTTP 200; 3 records; titles: Account Manager | Cyber Security Support Engineer | Enterprise Account Executive. JSON parser support required.

## Appcharge - unresolved

Source: https://www.appcharge.com/careers

Checked: 2026-09-09T13:42:37.954856+00:00

29 h3-containing blocks and embedded Comeet-synced records observed; Senior Account Manager, North America is a real card. Selector completeness/title extraction not verified.

## Riverside - solved

Source: https://www.riverside.fm/careers

Checked: 2026-09-09T13:42:39.302619+00:00

HTTP 200; 23 records; titles: Account Executive - EMEA | Agency Account Executive | Business Development Representative - Canada. JSON parser support required.

## Nexite - blocked

Source: https://www.nexite.io/careers

Checked: 2026-09-09T13:42:39.538321+00:00

HTTP 202 sparse response; serial browser captured no job-like requests. Suspected local access/challenge block; not proof no reachable board exists.
