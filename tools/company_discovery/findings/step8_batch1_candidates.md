# Step 8 batch 1 — candidate employers

Research date: 2026-09-25. Baseline: `config/companies.json` at commit `30bbe67`. This is a discovery/triage artifact, not an activation list. Every candidate below was checked against the existing company names. Evidence is restricted to employer-owned career sites and first-party ATS boards/APIs; no third-party job aggregators are used as evidence.

Disposition vocabulary:

- **Promote** — first-party job data and Israel hiring are both confirmed; good candidate for root-agent live verification.
- **Verify adapter** — Israel evidence is confirmed, but the frontend or ATS still needs endpoint/selector investigation.
- **Hold** — legitimate employer/site, but no current Israeli opening or no sufficiently stable extraction seam was confirmed.

## Strong API/ATS candidates

| # | Company | Official careers / first-party evidence | ATS or endpoint evidence | Israel evidence | Disposition |
|---:|---|---|---|---|---|
| 1 | DYG | [Comeet careers](https://www.comeet.com/jobs/dyg/58.009) | Confirmed Comeet board; the board ID is `dyg/58.009`. | Board has an Israel section and a Tel Aviv role. | **Promote** — existing Comeet adapter. |
| 2 | Port | [Comeet careers](https://www.comeet.com/jobs/port/59.004) | Confirmed Comeet board; `port/59.004`. | Multiple Tel Aviv engineering, data, product and IT roles. | **Promote**. |
| 3 | DriveNets | [Comeet careers](https://www.comeet.com/jobs/drivenets/72.006) | Confirmed Comeet board; `drivenets/72.006`. | Board exposes Raanana and Tel Aviv location groups, including entry-level roles. | **Promote**. |
| 4 | Rounds | [Comeet careers](https://www.comeet.com/jobs/rounds/59.005) | Confirmed Comeet board; `rounds/59.005`. | Tel Aviv location group with engineering/product roles. | **Promote**. |
| 5 | Elsight | [Comeet careers](https://www.comeet.com/jobs/elsight/B9.006) | Confirmed Comeet board; `elsight/B9.006`. | Ramat Gan, Israel openings in R&D and finance. | **Promote**. |
| 6 | Commit | [Comeet careers](https://www.comeet.com/jobs/comm-it/76.008) | Confirmed Comeet board; `comm-it/76.008`. | Large set of Petah Tikva, Tel Aviv, Haifa and other Israeli roles, including junior engineering. | **Promote**; high-volume board, test pagination/runtime. |
| 7 | Gett | [Comeet careers](https://www.comeet.com/jobs/gett/A0.002) | Confirmed Comeet board; `gett/A0.002`. | Tel Aviv, Israel positions across data, product, security and operations. | **Promote**. |
| 8 | Aitech | [Comeet posting](https://www.comeet.com/jobs/aitechsystems/88.004/talent-acquisition--temporary-position/15.275) | Confirmed Comeet tenant `aitechsystems/88.004`; promote only after board-level request succeeds. | First-party posting says Kfar Saba, Israel. | **Verify adapter** — board URL and counts. |
| 9 | Airobotics | [Comeet posting](https://www.comeet.com/jobs/airobotics/AA.005/ai-data-scientist/89.062) | Confirmed Comeet tenant `airobotics/AA.005`. | First-party roles are based in Petah Tikva. | **Promote** after board-level smoke test. |
| 10 | NewPhotonics | [Comeet careers](https://www.comeet.com/jobs/newphotonics/89.000) | Confirmed Comeet board; `newphotonics/89.000`. | Petah Tikva embedded-software and application-engineering roles. | **Promote**. |
| 11 | Pango | [Comeet posting](https://www.comeet.com/jobs/pango/59.002/engineering-tl--growth-team/12.C62) | Confirmed Comeet tenant `pango/59.002`. | First-party posting is Petah Tikva, Israel. | **Promote** after board-level smoke test. |
| 12 | abra R&D | [Comeet posting](https://www.comeet.com/jobs/abra_rnd/15.007/integration-engineer--north/60.D62) | Confirmed Comeet tenant `abra_rnd/15.007`. | Posting is Haifa, Haifa District, IL. | **Promote** after board-level smoke test. |
| 13 | Tabnine | [Official careers](https://www.tabnine.com/careers/) / [Comeet board](https://www.comeet.com/jobs/tabnine/39.006) | Confirmed Comeet board; `tabnine/39.006`. | Board lists Tel Aviv engineering and applied-research roles. | **Promote**. |
| 14 | BioCatch | [Official careers](https://www.biocatch.com/cybersecurity-careers) / [Comeet board](https://www.comeet.com/jobs/biocatch/03.00E) / [Lever board](https://jobs.lever.co/biocatch) | A live Comeet tenant `biocatch/03.00E` and a live Lever tenant are both visible; canonical/deduplication behavior must be checked before activation. | Both first-party ATS surfaces contain Tel Aviv R&D/data roles. | **Promote after canonical-feed check** — prefer Comeet if it is complete. |
| 15 | Axonius | [Official open jobs](https://www.axonius.com/company/careers/open-jobs) / [Greenhouse application](https://boards.greenhouse.io/embed/job_app?for=axonius&token=6592311003) | Confirmed Greenhouse token `axonius`. API candidate: `https://boards-api.greenhouse.io/v1/boards/axonius/jobs?content=true`. | Official page lists numerous Tel Aviv engineering, research and product roles. | **Promote** — generic Greenhouse mapping. |
| 16 | Bosch Israel | [Bosch Israel SmartRecruiters portal](https://careers.smartrecruiters.com/BoschGroup/israel) | Confirmed SmartRecruiters company `BoschGroup`; API candidate: `https://api.smartrecruiters.com/v1/companies/BoschGroup/postings`. | First-party portal is explicitly the Bosch Israel job portal. | **Promote** after API location/count verification. |
| 17 | Radware | [Official careers](https://www.radware.com/careers/) / [Taleo job search](https://radware.taleo.net/careersection/ex/joblist.ftl) | Confirmed Oracle Taleo frontend, not covered by current generic ATS mappings. | Taleo results include multiple `IL-IL-Tel Aviv` roles. | **Verify adapter** — Taleo pagination/contract. |
| 18 | Classiq | [Official careers](https://www.classiq.io/careers-page) / [Comeet board](https://www.comeet.com/jobs/classiq/F7.008) | Confirmed Comeet tenant `classiq/F7.008`. | First-party board lists numerous Product & R&D roles in Israel. | **Promote**. |
| 19 | AI21 Labs | [Official careers](https://www.ai21.com/careers/) | Official job paths include Comeet-like position IDs, but a public board/API must still be confirmed. | Official careers content lists Tel Aviv algorithms and engineering roles. | **Verify adapter**. |
| 20 | Personetics | [Official careers](https://personetics.com/careers/) / [SmartRecruiters tenant](https://careers.smartrecruiters.com/Personetics) | SmartRecruiters tenant exists, but currently exposes no postings while the employer site does; likely custom/embedded feed. | Employer page lists many Tel Aviv R&D, product and data roles. | **Verify adapter** — do not use the empty SR tenant blindly. |

## Confirmed employer sites needing selector/API investigation

| # | Company | Official careers / first-party evidence | ATS or endpoint evidence | Israel evidence | Disposition |
|---:|---|---|---|---|---|
| 21 | Aqua Security | [Official careers](https://www.aquasec.com/about-us/careers/) / [Comeet board](https://www.comeet.com/jobs/aquasec/91.001) | Confirmed Comeet tenant `aquasec/91.001`. | Page and ATS expose several Ramat Gan, Israel engineering and security roles. | **Promote**. |
| 22 | Deep Instinct | [Official careers](https://www.deepinstinct.com/careers) | Employer-hosted careers page; no stable public ATS endpoint confirmed in this pass. | Page states operations in Tel Aviv; current visible openings may be US-only. | **Hold** until an Israeli role/API appears. |
| 23 | Playtika | [Official positions](https://www.playtika.com/position/) / [current careers frontend](https://playtika.teamme.link/) | Teamme/custom frontend; endpoint not confirmed. | First-party page exposes Israel/Herzliya openings. | **Verify adapter**. |
| 24 | RAD Data Communications | [Official careers](https://www.rad.com/career/) | Employer-hosted searchable job list; selector/API inspection needed. | Official page states most staff work at Tel Aviv, Jerusalem and Be'er Sheva sites and lists current Israel jobs. | **Verify adapter**. |
| 25 | Dell Technologies Israel | [Official job search](https://jobs.dell.com/en/search-jobs?fc=56067%2C11751%2C35234%2C24333%2C52058%2C70908) | Frontend routes applications through Dell's Oracle Candidate Experience host; exact Recruiting Cloud site/parameters still need discovery. | Official search lists Israel roles in Herzliya, Haifa and Beer Sheba, including graduate software engineering. | **Verify ORC parameters**, high priority for early-career relevance. |
| 26 | Arm Israel | [Official Israel search](https://careers.arm.com/location/israel-jobs/33099/294640/2) | Phenom-like employer frontend; no direct JSON endpoint confirmed. | Official page has Raanana hardware, research and software roles. | **Verify adapter**. |
| 27 | Innoviz Technologies | [Official careers](https://innoviz.tech/careers) / [positions](https://innoviz.tech/join-us) | Employer-hosted job list; API/selector inspection required. | Official positions are explicitly in Israel. | **Verify adapter**. |
| 28 | StoreDot | [Official careers](https://www.store-dot.com/careers) | Employer-hosted filtered positions; no ATS endpoint confirmed. | Official page identifies Herzliya as an R&D location. | **Verify adapter**; currently appears low-volume. |
| 29 | Freightos | [Official careers](https://www.freightos.com/careers/) | Employer-hosted openings widget; endpoint not confirmed. | Employer is Jerusalem-rooted, but the current page needs live inspection to confirm Israel openings and locations. | **Hold** pending current Israel-role proof. |
| 30 | OrCam | [Official careers](https://careers.orcam.com/) | Separate first-party careers host; current extraction seam not confirmed. | Official careers host belongs to the Jerusalem-based R&D employer. | **Verify adapter**. |
| 31 | Nayax | [Official careers](https://www.nayax.com/careers/) | Employer-hosted loading widget; underlying feed requires sniffing. | Official page says Israel is its largest site and that product development is in Herzliya; Israel openings are exposed. | **Verify adapter**. |
| 32 | Earnix | [Official Israel careers](https://earnix.com/our-story/careers/israel/) | Employer-hosted careers frontend; endpoint not confirmed. | Official page lists Ramat Gan engineering/data roles. | **Verify adapter**. |
| 33 | Fundbox | [Official careers](https://fundbox.com/careers/) | Employer-hosted job widget; endpoint not confirmed. | Tel Aviv is a first-party location, but current visible openings in this snapshot are US-only. | **Hold** until an Israeli opening is present. |
| 34 | Dataloop | [Official careers](https://dataloop.ai/careers/) | Employer-hosted positions array. | Official contact page identifies Herzliya, but careers currently says no openings. | **Hold** — legitimate future candidate, zero current jobs. |
| 35 | Ericsson Israel | [Israel presence](https://www.ericsson.com/en/about-us/company-facts/ericsson-worldwide/israel) / [official jobs](https://jobs.ericsson.com/) | Global custom careers platform. | First-party Israel page confirms the Rosh Ha'ayin office; current Israeli openings were not established. | **Hold** pending job evidence. |
| 36 | Nokia Israel | [Official careers](https://www.nokia.com/careers/) | Global custom careers platform. | Israel activity is plausible, but this pass did not find a first-party current Israel result. | **Hold**; do not activate without direct job evidence. |
| 37 | Lam Research Israel | [Official careers](https://careers.lamresearch.com/) | Enterprise careers frontend; its first-party configuration includes Israel among location conditions. | Israel is represented in the careers configuration, but current role evidence needs a filtered live query. | **Hold/verify**. |
| 38 | ASML Israel | [Official careers](https://www.asml.com/en/careers) | Global custom careers platform. | No first-party current Israel result was confirmed in this pass. | **Hold**. |
| 39 | Team8 | [Comeet portfolio board](https://www.comeet.com/jobs/team8/61.003) | Confirmed Comeet board, but it mixes Team8 and portfolio-company roles. | Many Tel Aviv jobs, including junior roles, are present. | **Hold as a company record**; consider a separate discovery feed to avoid misattribution. |
| 40 | Outbrain | [Official company/careers entry](https://www.outbrain.com/about/) | Careers link exists, but Outbrain is now part of Teads and Teads already exists in the catalog. | First-party corporate material confirms a substantial Israel workforce. | **Reject/merge review** — likely duplicate coverage under Teads. |

## Additional verified non-duplicate candidates

| # | Company | Official careers / first-party evidence | ATS or endpoint evidence | Israel evidence | Disposition |
|---:|---|---|---|---|---|
| 41 | Atera | [Official careers](https://www.atera.com/careers/) / [Comeet board](https://www.comeet.com/jobs/atera/63.00B) | Embedded Comeet tenant `atera/63.00B`. | Official page currently lists Tel Aviv roles. | **Promote**, but verify one stale job URL observed during research. |
| 42 | Hello Heart | [Official careers](https://www.helloheart.com/about/careers) / [Greenhouse board](https://job-boards.greenhouse.io/helloheart) | Confirmed Greenhouse token `helloheart`; API candidate `https://boards-api.greenhouse.io/v1/boards/helloheart/jobs?content=true`. | Board lists Tel Aviv QA, mobile, product and ML roles. | **Promote**. |
| 43 | Echo | [Comeet board](https://www.comeet.com/jobs/echo/9A.006) | Confirmed Comeet tenant `echo/9A.006`. | Live board contains Tel Aviv engineering/security roles. | **Promote**; confirm the intended company identity/brand before assigning an ID. |
| 44 | Akeyless | [Official careers](https://www.akeyless.io/careers/) / [Comeet board](https://www.comeet.com/jobs/akeyless/27.006) | Confirmed Comeet tenant `akeyless/27.006`. | First-party sources list multiple Ramat Gan roles. | **Promote**. |
| 45 | LayerX Security | [Official careers](https://layerxsecurity.com/careers/) / [Comeet board](https://www.comeet.com/jobs/layerxsecurity/F9.00D) | Confirmed Comeet tenant `layerxsecurity/F9.00D`. | ATS lists multiple Tel Aviv R&D jobs. | **Promote**. |
| 46 | Cross River | [Official careers](https://www.crossriver.com/careers) / [Israel Comeet board](https://www.comeet.com/jobs/crossriver/C7.00F) | Confirmed Israel-specific Comeet tenant `crossriver/C7.00F`; US jobs use a separate feed. | Employer page describes its Jerusalem development team and the ATS lists Jerusalem roles. | **Promote** using only the Israel Comeet feed. |
| 47 | Remedio | [Comeet board](https://www.comeet.com/jobs/remedio/CA.000) | Confirmed Comeet tenant `remedio/CA.000`. | Live first-party board contains Tel Aviv security/R&D roles. | **Promote**. |
| 48 | Kayhut | [Comeet board](https://www.comeet.com/jobs/Kayhut/F0.00B) | Confirmed Comeet tenant `Kayhut/F0.00B`. | Live board lists Herzliya, Israel. | **Promote**. |
| 49 | A Security | [Comeet board](https://www.comeet.com/jobs/a_security/EA.007) | Confirmed Comeet tenant `a_security/EA.007`. | Live security-research role is Tel Aviv-Yafo, IL. | **Verify identity first** — brand name is too ambiguous for a safe catalog ID. |
| 50 | Clover Security | [Comeet board](https://www.comeet.com/jobs/clover_security/7A.00A) | Confirmed Comeet tenant `clover_security/7A.00A`. | Live board contains Israel/Tel Aviv roles. | **Promote** after company-domain identity check. |
| 51 | Backslash Security | [Comeet board](https://www.comeet.com/jobs/backslash/98.004) | Confirmed Comeet tenant `backslash/98.004`. | Live R&D role is in Tel Aviv-Yafo. | **Promote**. |
| 52 | Oligo Security | [Official careers](https://www.oligo.security/company/careers) / [Comeet board](https://www.comeet.com/jobs/oligosecurity/5A.00B) | Confirmed Comeet tenant `oligosecurity/5A.00B`. | First-party sources list numerous Tel Aviv positions. | **Promote**. |
| 53 | Pentera | [Official careers](https://pentera.io/careers/) / [Comeet board](https://www.comeet.com/jobs/pentera/C5.00D) | Confirmed Comeet tenant `pentera/C5.00D`. | Board lists Israel engineering, product and security roles. | **Promote**. |
| 54 | Zero Networks | [Official careers](https://zeronetworksit.com/careers) / [Comeet board](https://www.comeet.com/jobs/zeronetworks/39.00F) | Confirmed Comeet tenant `zeronetworks/39.00F`. | First-party sources list multiple Tel Aviv/Ramat Gan roles. | **Promote**. |
| 55 | Moon Active | [Official careers](https://www.moonactive.com/careers/) | Confirmed Ashby job board; API candidate `https://api.ashbyhq.com/posting-api/job-board/moonactive`. | Live first-party data contains Tel Aviv backend/security roles. | **Promote** — generic Ashby mapping. |
| 56 | MongoDB | [Official jobs](https://www.mongodb.com/company/careers/see-jobs) | Confirmed Greenhouse token `mongodb`; API candidate `https://boards-api.greenhouse.io/v1/boards/mongodb/jobs?content=true`. | Official jobs page supports Tel Aviv/Israel and has a current role. | **Promote** — generic Greenhouse mapping. |
| 57 | CrowdStrike | [Official careers](https://www.crowdstrike.com/en-us/careers/) | Confirmed Workday CXS endpoint: `https://crowdstrike.wd5.myworkdayjobs.com/wday/cxs/crowdstrike/crowdstrikecareers/jobs`. | Current first-party data contains Israel–Tel Aviv engineering roles. | **Promote** — generic Workday mapping. |
| 58 | Mastercard | [Official Tel Aviv careers](https://careers.mastercard.com/us/en/tel-aviv-israel) | Confirmed Workday CXS endpoint: `https://mastercard.wd1.myworkdayjobs.com/wday/cxs/mastercard/CorporateCareers/jobs`. | Official page currently reports Israel jobs. | **Promote** — generic Workday mapping. |
| 59 | SuperPlay | [Official careers](https://www.superplay.co/careers/) / [Comeet board](https://www.comeet.com/jobs/superplay/28.003) | Confirmed Comeet tenant `superplay/28.003`. | Board contains multiple Tel Aviv jobs, including entry-level openings. | **Promote**. |
| 60 | Nova Ltd. | [Official Israel positions](https://nova.co.il/location_filter/israel/) | First-party WordPress job board; no generic ATS API confirmed. | Israel-filtered page contains a large set of Rehovot positions. | **Verify adapter** — strong volume, custom/browser likely. |
| 61 | AudioCodes | [Official careers](https://www.audiocodes.com/careers) | Employer-owned job board and detail routes; no generic API confirmed. | First-party board contains multiple Or Yehuda positions. | **Verify adapter**. |
| 62 | Snowflake | [Official EMEA careers](https://careers.snowflake.com/us/en/emea-jobs) | First-party careers site appears to mix requisition integrations; stable public API not confirmed. | Tel Aviv office/current Israel role observed, but volume is low. | **Hold/inspect network**. |
| 63 | HP Inc. / Indigo | [Official HP jobs](https://jobs.hp.com/) | HP first-party candidate site uses `apply.hp.com/careers/job/<id>` routes; endpoint discovery required. | Current first-party results include Kiryat Gat/Ness Ziona positions, including a student researcher. | **Verify adapter**, valuable early-career target. |

## Notes for activation verification

1. Prefer candidates 1–16 and 41–59 where marked Promote: they have concrete ATS seams compatible with existing adapters or close variants.
2. For every API candidate, root-agent verification should record HTTP status, total count, unique IDs, empty title/location rate, and at least one Israeli sample before editing `companies.json`.
3. Do not activate portfolio aggregators (notably Team8) as if every posting belongs to the parent employer.
4. `Personetics` demonstrates why a recognizable ATS hostname alone is insufficient: its SmartRecruiters tenant is empty while its official site has live jobs.
5. `Outbrain` requires ownership/deduplication treatment because the existing catalog already includes Teads.

## Activation result

The root-agent verification exercised every promoted entry through
`fetch_jobs_from_company()`, not just through a raw page request. The final
batch contains 44 companies: 29 Comeet, 11 Greenhouse, two Ashby, and two
Workday routes. Every activated route returned `SUCCESS`, at least one live
job, unique non-empty IDs, non-empty titles, and an Israeli sample recognized
by the production location vocabulary.

| ATS | Activated company IDs |
|---|---|
| Comeet | `port`, `drivenets`, `rounds`, `elsight`, `commit`, `gett`, `aitech`, `airobotics`, `newphotonics`, `pango`, `abra_rnd`, `biocatch`, `classiq`, `aqua_security`, `atera`, `akeyless`, `cross_river`, `remedio`, `kayhut`, `backslash_security`, `oligo_security`, `pentera`, `zero_networks`, `superplay`, `fetcherr`, `navina`, `nym_health`, `windward`, `clover_security` |
| Greenhouse | `apiiro`, `axonius`, `eleos_health`, `hello_heart`, `mongodb`, `nanit`, `pendo`, `token_security`, `torii`, `wedev`, `wolt_israel` |
| Ashby | `moon_active`, `finout` |
| Workday | `crowdstrike`, `mastercard` |

Post-activation correction (2026-09-26): the original `woltisrael` token was
later proven to be Wolt's Israel warehouse/store/support board, not its
engineering organization. The catalog now uses the canonical global `wolt`
Greenhouse board and retains strict Israel filtering. See
[`wolt_engineering_board.md`](wolt_engineering_board.md) for the first-party
evidence and live comparison.

Live job counts ranged from one (`newphotonics`, `torii`) to 402 (`mongodb`).
All 44 boards had a one-to-one job-count/unique-ID count. Three Comeet feeds
contained a small number of individual records without location data
(`elsight`: 1, `kayhut`: 4, `backslash_security`: 1); their other records
provided verified Israeli locations, while the strict downstream location
gate safely rejects the unlocated records.

Candidates deliberately not activated after live adapter verification:

- `dyg`, `tabnine`, and `layerx_security`: valid Comeet boards but currently
  returned `NO_JOBS`.
- Bosch Israel: the generic SmartRecruiters company feed returned 4,796
  global jobs and neither `q=Israel` nor ISO-country filtering returned a
  current Israeli posting; activating it would add cost without usable data.
- `frontegg`, `overwolf`, `minute_media`, `groundcover`, and `healthy_io`:
  their detected Comeet integrations currently returned `NO_JOBS` through
  the production adapter.
- Playtika, Radware, Personetics, Nova, AudioCodes, and the other
  **Verify adapter** entries remain separate follow-up work; none was
  force-fitted into an existing mapping.
