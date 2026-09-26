# Step 8 batch 2 — candidate employers

Research date: 2026-09-26. Baseline: `config/companies.json` at commit
`ce6fcec` (279 records). This is a discovery artifact, not an activation list.
Every name below was checked against the current catalog and against
`step8_batch1_candidates.md`; batch-1 candidates are intentionally not recycled.
Evidence is restricted to employer-owned careers pages and first-party ATS
boards/APIs.

Disposition vocabulary:

- **Promote** — an existing adapter has a concrete endpoint and the first-party
  feed currently contains at least one Israeli job. The root agent still needs
  to exercise it through `fetch_jobs_from_company()` before activation.
- **Verify adapter** — the official careers page has current Israeli work, but
  the stable extraction seam or canonical feed still needs confirmation.
- **Hold** — no current Israeli opening, an empty/stale feed, ambiguous identity,
  or a likely parent/subsidiary duplicate.

## Promote-ready: Comeet

The URLs in this table are the first-party Comeet boards themselves. The
recently optimized Comeet adapter already supports this shape.

| # | Company | First-party endpoint | Live Israel evidence | Disposition |
|---:|---|---|---|---|
| 1 | Buildots | [Comeet `buildots/36.004`](https://www.comeet.com/jobs/buildots/36.004); [official careers](https://buildots.com/careers/) | Official page and board list multiple Tel-Aviv development, product, operations and finance roles. | **Promote**. |
| 2 | Vi | [Comeet `vi/B1.002`](https://www.comeet.com/jobs/vi/B1.002) | Five current Tel Aviv roles, including AI Engineer, Data Analyst and Data Engineering. | **Promote**. |
| 3 | Automat-it | [Comeet `automatit/26.003`](https://www.comeet.com/jobs/automatit/26.003) | Four current Tel-Aviv, Israel roles. | **Promote**. |
| 4 | Sentra | [Comeet `sentra/87.00B`](https://www.comeet.com/jobs/sentra/87.00B); [official careers](https://www.sentra.io/careers) | Current Tel Aviv engineering/product roles. A separate Ashby `sentra` board has three jobs but no Israeli locations, so Comeet appears to be the complete Israel feed; verify counts before activation and activate only one. | **Promote after canonical-feed check**. |
| 5 | Dream | [Comeet `dreamgroup/99.002`](https://www.comeet.com/jobs/dreamgroup/99.002) | Large current Tel Aviv / `TLV - ISR` cyber, AI and engineering set. Final exact-URL duplicate checking found that this endpoint is already configured as `dream_security`. | **Reject as duplicate coverage**; the earlier assumption that these were unrelated employers was incorrect. |
| 6 | Tastewise | [Comeet `tastewise/F8.000`](https://www.comeet.com/jobs/tastewise/F8.000); [official careers](https://tastewise.io/careers) | Three current Tel Aviv, Israel roles in product and R&D. | **Promote**. |
| 7 | Shopic | [Comeet `shopic/E6.002`](https://www.comeet.com/jobs/shopic/E6.002) | Two current Tel-Aviv R&D roles. | **Promote**. |
| 8 | CHEQ | [Comeet `cheq/65.005`](https://www.comeet.com/jobs/cheq/65.005) | Three current Tel Aviv roles, including AI Engineer and Senior Fullstack Engineer. | **Promote**. |
| 9 | Guardio | [Comeet `guardio/57.000`](https://www.comeet.com/jobs/guardio/57.000) | Twenty-four current Tel-Aviv, Israel roles; the board includes an entry-level IT role. | **Promote**. |
| 10 | Zenity | [Comeet `zenity/19.000`](https://www.comeet.com/jobs/zenity/19.000) | Ten current Tel Aviv roles across engineering, AI research, product and finance. | **Promote**. |
| 11 | Upstream Security | [Comeet `upstream/E4.003`](https://www.comeet.com/jobs/upstream/E4.003) | Three Herzliya roles, including a Data Analyst student position. | **Promote**, particularly relevant to the early-career feed. |
| 12 | Orchid Security | [Comeet `orchid_security/4A.001`](https://www.comeet.com/jobs/orchid_security/4A.001) | Current Tel-Aviv R&D roles in AI, backend and endpoint software. | **Promote**. |
| 13 | Onyx Security | [Comeet `onyxsecurity/BA.005`](https://www.comeet.com/jobs/onyxsecurity/BA.005) | Current Tel Aviv engineering, AI, product and operations roles. | **Promote**. |
| 14 | Surecomp | [Comeet `Surecomp/24.00E`](https://www.comeet.com/jobs/Surecomp/24.00E) | Current Kfar Saba role; first-party posting explicitly identifies the Israel office. | **Promote**. |
| 15 | Rapid Medical | [Comeet `rapidmedical/5A.003`](https://www.comeet.com/jobs/rapidmedical/5A.003) | Current Yokneam, Israel roles including entry-level manufacturing. | **Promote**. |
| 16 | MedOne | [Comeet `medone/58.006`](https://www.comeet.com/jobs/medone/58.006) | The production adapter returned 2 jobs, but neither passed the strict Israel location filter in the final verification. | **Hold**; zero production-recognized Israel jobs. |
| 17 | Landa Digital Printing | [Comeet `landacorp/A4.000`](https://www.comeet.com/jobs/landacorp/A4.000) | Five current Rehovot roles, including two student positions and software engineering. | **Promote**. |
| 18 | AT&T Israel | [Comeet `joinattil/38.00A`](https://www.comeet.com/jobs/joinattil/38.00A) | Current Airport City / Tel Aviv engineering, product and cyber roles. | **Promote**; distinct employer feed, not the existing DriveNets record. |
| 19 | BlinkOps | [Comeet `blinkops/C7.004`](https://www.comeet.com/jobs/blinkops/C7.004) | Current Tel-Aviv backend engineering and product roles. | **Promote**. |
| 20 | Finubit | [Comeet `finubit/A9.002`](https://www.comeet.com/jobs/finubit/A9.002) | Current Tel Aviv engineering roles; the board identifies the company as Bank Leumi-backed but a separate operating company. | **Promote**, subject to ordinary employer-identity check. |
| 21 | Plaee | [Comeet `plaee/5B.004`](https://www.comeet.com/jobs/plaee/5B.004) | Current Ramat Gan first-party posting. | **Promote** after board-level count check. |
| 22 | Tenengroup | [Comeet `Tenengroup/93.00C`](https://www.comeet.com/jobs/Tenengroup/93.00C) | The board returned jobs successfully, but the later target-role audit found only jewelry, retail, finance, purchasing, and marketing titles with zero software/data/product/security matches. | **Deactivated — no target-role jobs**. The working ATS does not make this a high-tech employer feed. |

## Promote-ready: Greenhouse

All API counts below were re-read live from Greenhouse on 2026-09-26.

| # | Company | First-party API | Live result | Disposition |
|---:|---|---|---|---|
| 23 | Innovid | [`innovid` API](https://boards-api.greenhouse.io/v1/boards/innovid/jobs?content=true) | 7 jobs; 1 Software Engineer in Ramat Gan. | **Promote**. |
| 24 | BeamUP | [`beamup` API](https://boards-api.greenhouse.io/v1/boards/beamup/jobs?content=true) | 4/4 jobs are in Tel Aviv/Israel, including applied AI and data science. | **Promote**. |
| 25 | Credible | [`credible` API](https://boards-api.greenhouse.io/v1/boards/credible/jobs?content=true) | 12 jobs; 2 include Tel Aviv, Israel. | **Promote**. |
| 26 | Nift | [`nift` API](https://boards-api.greenhouse.io/v1/boards/nift/jobs?content=true) | 13 jobs; 3 Israel jobs in data science/data/ML Ops. | **Promote**. |
| 27 | Guidde | [`guidde` API](https://boards-api.greenhouse.io/v1/boards/guidde/jobs?content=true) | 9 jobs; 4 Tel Aviv roles. | **Promote**. |
| 28 | Unframe | [`unframe` API](https://boards-api.greenhouse.io/v1/boards/unframe/jobs?content=true) | 35 jobs; 11 in Tel Aviv-Yafo. | **Promote**. |
| 29 | Honeycomb Insurance | [`honeycombinsurance` API](https://boards-api.greenhouse.io/v1/boards/honeycombinsurance/jobs?content=true) | 13 jobs; 2 current Tel Aviv engineering jobs. | **Promote**. |
| 30 | Sweet Security | [`sweetsecurity` API](https://boards-api.greenhouse.io/v1/boards/sweetsecurity/jobs?content=true); [official careers](https://www.sweet.security/career) | 3 live jobs; 2 in Tel-Aviv. The human-facing board is on Greenhouse's EU hostname, but the normal public API hostname answers successfully. | **Promote**. |
| 31 | Obligo | [`obligo` API](https://boards-api.greenhouse.io/v1/boards/obligo/jobs?content=true) | 3 jobs; 2 current Tel Aviv product roles. | **Promote**. |
| 32 | Oasis Security | [`oasissecurity` API](https://boards-api.greenhouse.io/v1/boards/oasissecurity/jobs?content=true) | 3/3 jobs in Tel Aviv. | **Promote**. |
| 33 | Conifers.ai | [`conifersaicareers` API](https://boards-api.greenhouse.io/v1/boards/conifersaicareers/jobs?content=true) | 4 jobs; 3 current Tel Aviv AI/security roles. | **Promote**. |
| 34 | GitLab | [`gitlab` API](https://boards-api.greenhouse.io/v1/boards/gitlab/jobs?content=true) | The production adapter returned 199 jobs, but zero passed the strict Israel location filter; the earlier raw-payload count matched descriptive text rather than normalized job locations. | **Hold**; no production-recognized Israel jobs. |

## Promote-ready: Ashby

| # | Company | First-party API | Live result | Disposition |
|---:|---|---|---|---|
| 35 | Unit | [`unit` API](https://api.ashbyhq.com/posting-api/job-board/unit) | 3 jobs; 2 at Tel Aviv Office. | **Promote**. |
| 36 | Chainalysis | [`chainalysis-careers` API](https://api.ashbyhq.com/posting-api/job-board/chainalysis-careers) | 52 jobs; 7 at Tel Aviv Office, including the Alterya R&D team. | **Promote** under Chainalysis only; do not add a second Alterya employer ID. |
| 37 | Nexxen | [`nexxen` API](https://api.ashbyhq.com/posting-api/job-board/nexxen) | 28 jobs; 7 in Tel Aviv, Israel. | **Promote**; distinct from the existing Teads/Outbrain lineage. |
| 38 | Airwallex | [`airwallex` API](https://api.ashbyhq.com/posting-api/job-board/airwallex) | 578 jobs; 9 tagged `IL - Tel Aviv`. | **Promote**, but note the high global volume when measuring pipeline cost. |
| 39 | Viz.ai | [`Viz.ai` API](https://api.ashbyhq.com/posting-api/job-board/Viz.ai); [official job](https://jobs.ashbyhq.com/Viz.ai/4453691a-998c-42b4-916c-b2bc25340557/) | 16 jobs; 7 in Tel Aviv. | **Promote**. |

## Promote-ready: Workable

These listing APIs require `POST {}` just like the two existing Workable
companies. Live counts were recorded on 2026-09-26.

| # | Company | First-party API | Live result | Disposition |
|---:|---|---|---|---|
| 40 | Autofleet | [`autofleet` API](https://apply.workable.com/api/v3/accounts/autofleet/jobs); [first-party posting](https://apply.workable.com/autofleet/j/6385BE88E4/) | 10 jobs; 9 in Tel Aviv-Yafo. | **Promote**. |
| 41 | Tomax | [`tomax` API](https://apply.workable.com/api/v3/accounts/tomax/jobs); [first-party posting](https://apply.workable.com/tomax/j/ED06704A79/) | 8/8 jobs in Israel (Sarid/Kfar Monash area). | **Promote**; verify that the existing location vocabulary recognizes the returned city strings. |
| 42 | Nuvei | [`nuvei` API](https://apply.workable.com/api/v3/accounts/nuvei/jobs); [first-party posting](https://apply.workable.com/nuvei/j/6CDEE23387/) | 10 jobs; 2 in Tel Aviv-Yafo. | **Promote**. |
| 43 | REAL | [`real-dev-inc` API](https://apply.workable.com/api/v3/accounts/real-dev-inc/jobs); [first-party posting](https://apply.workable.com/real-dev-inc/j/2A25A7E20F) | 7 jobs; 6 in Tel Aviv-Yafo. | **Hold** until the generic catalog-facing company name and domain are unambiguous. |

## Current Israel work, but extraction/canonical source needs investigation

| # | Company | Primary evidence | What remains | Disposition |
|---:|---|---|---|---|
| 44 | Pecan AI | [Official careers](https://www.pecan.ai/careers/) | The page currently lists several Ramat Gan roles and older pages carry Greenhouse `gh_jid` parameters, but obvious board tokens now return 404. Sniff the current embedded feed instead of guessing a token. | **Verify adapter**. |
| 45 | Trigo | [Official careers](https://www.trigo.tech/career/) | Current Israel R&D/product roles are rendered on an employer-owned page; stable API/selector not yet established. | **Verify adapter**. |
| 46 | Growthspace | [Official careers](https://www.growthspace.com/careers) | One current Tel Aviv opening on a custom page. Determine whether the rendered card has a stable detail route. | **Verify adapter**. |
| 47 | Scytale | [Official careers](https://scytale.ai/scytale-careers/) | Current Tel Aviv role and employer-owned `/careers/co/...` detail routes; determine the underlying ATS/API before activation. | **Verify adapter**. |
| 48 | Anecdotes | [Official careers](https://www.anecdotes.ai/careers) | Current Tel Aviv roles; job links carry a Greenhouse source parameter, but `anecdotes` is not a live public-board token. Inspect the live integration. | **Verify adapter**. |
| 49 | OneLayer | [Official careers](https://onelayer.com/careers/) | Official Tel Aviv office and opening section confirmed, but current cards/feed were not exposed in the static response. | **Verify adapter**. |
| 50 | Foretellix | [Official careers](https://www.foretellix.com/careers/) | Employer careers page is WAF-protected in a simple request. Browser/network inspection is needed; do not force it into an API mapping. | **Verify adapter**. |
| 51 | TytoCare | [Official careers](https://www.tytocare.com/careers/) | Employer-owned jobs component confirmed; ATS identifier was not exposed in static HTML. | **Verify adapter**. |
| 52 | Ibex Medical Analytics | [Official careers](https://ibex-ai.com/careers/) | Official careers page currently blocks simple HTTP requests with 403; inspect by browser. | **Verify adapter / possible WAF**. |
| 53 | MDClone | [Official careers](https://www.mdclone.com/careers/) | Employer-owned careers surface; live endpoint and current Israel count still need network inspection. | **Verify adapter**. |
| 54 | Diagnostic Robotics | [Official careers](https://www.diagnosticrobotics.com/careers) | Employer-owned careers surface; stable feed not confirmed. | **Verify adapter**. |
| 55 | Sweetch | [Official careers](https://www.sweetch.com/careers) | Employer-owned careers surface; stable feed and current Israel sample need confirmation. | **Verify adapter**. |
| 56 | Binah.ai | [Official careers](https://www.binah.ai/careers/) | Employer-owned careers surface; stable job-data endpoint not confirmed. | **Verify adapter**. |
| 57 | Medisafe | [Official careers](https://www.medisafe.com/careers/) | Employer-owned careers surface; inspect current posting source and Israel count. | **Verify adapter**. |
| 58 | Nanox | [Official careers](https://www.nanox.vision/careers/) | Employer-owned careers surface; endpoint and current Israel count need verification. | **Verify adapter**. |
| 59 | Cymbio | [Official careers](https://www.cymbio.com/careers/) | Employer-owned careers surface; no supported public feed confirmed in this pass. | **Verify adapter**. |
| 60 | Trullion | [Official careers](https://trullion.com/careers/) | Employer-owned careers surface; identify canonical job feed and Israel count. | **Verify adapter**. |
| 61 | Lili | [Official careers](https://www.lili.co/careers) | Employer-owned careers surface; stable ATS endpoint not found from static source. | **Verify adapter**. |
| 62 | Riverside | [Official careers](https://riverside.fm/careers) | Employer-owned careers surface; stable endpoint not confirmed. | **Verify adapter**. |
| 63 | DustPhotonics | [Official careers](https://www.dustphotonics.com/careers) | Israeli semiconductor employer; current job feed needs inspection. | **Verify adapter**. |
| 64 | NeuReality | [Official careers](https://neureality.ai/careers/) | Israeli AI-infrastructure employer; no supported endpoint confirmed. | **Verify adapter**. |
| 65 | Xsight Labs | [Official careers](https://www.xsightlabs.com/careers/) | Israeli semiconductor employer; inspect rendered jobs/network feed. | **Verify adapter**. |
| 66 | Chain Reaction | [Official careers](https://www.chain-reaction.io/careers/) | Israeli semiconductor employer; stable feed not confirmed. | **Verify adapter**. |
| 67 | SatixFy | [Official careers](https://www.satixfy.com/careers/) | Employer-owned careers surface; current Israel roles/feed require verification. | **Verify adapter**. |
| 68 | Inuitive | [Official careers](https://www.inuitive-tech.com/careers/) | Israeli vision-chip employer; stable endpoint not confirmed. | **Verify adapter**. |
| 69 | XTEND | [Official careers](https://www.xtend.me/careers/) | Israeli robotics/defense employer; current posting feed requires inspection. | **Verify adapter**. |
| 70 | NextVision | [Official careers](https://nextvision-sys.com/careers/) | Employer-owned careers surface; no generic ATS seam confirmed. | **Verify adapter**. |
| 71 | UVision | [Official careers](https://uvisionuav.com/careers/) | Employer-owned careers surface; endpoint/current Israel job sample needs verification. | **Verify adapter**. |
| 72 | Tomorrow.io | [Official careers](https://www.tomorrow.io/careers/) | Multinational with Israeli roots; current canonical board and Israel locations need confirmation. | **Verify adapter**. |
| 73 | Electreon | [Official careers](https://electreon.com/careers/) | Israeli mobility employer; stable posting endpoint not confirmed. | **Verify adapter**. |
| 74 | H2Pro | [Official careers](https://h2pro.co/careers/) | Israeli climate-tech employer; current roles/feed need verification. | **Verify adapter**. |
| 75 | Nano Dimension | [Official careers](https://www.nano-di.com/careers) | Employer-owned global careers page; isolate the Israel feed and inspect the underlying ATS. | **Verify adapter**. |
| 76 | Highcon | [Official careers](https://www.highcon.net/careers/) | Israeli industrial-tech employer; current roles/feed need confirmation. | **Verify adapter**. |
| 77 | Massivit 3D | [Official careers](https://www.massivit3d.com/careers/) | Employer-owned careers page; stable endpoint not confirmed. | **Verify adapter**. |
| 78 | Augmedics | [Official careers](https://augmedics.com/careers/) | Israeli-founded medical-tech employer; canonical board and current Israel jobs need confirmation. | **Verify adapter**. |

## Deliberate holds, zero feeds, and ownership conflicts

| # | Company | Primary evidence / live check | Reason not to activate |
|---:|---|---|---|
| 79 | Knostic | [Official careers](https://www.knostic.ai/careers) | Official page says to stay tuned for 2026 opportunities but exposes no concrete live jobs. **Hold — zero current board**. |
| 80 | Astrix Security | [Official careers](https://astrix.security/careers/) | Official page currently says “No jobs found”; the company also states it is now part of Cisco. **Hold — zero jobs and likely Cisco ownership overlap**. |
| 81 | CyberArk | [Official careers](https://www.cyberark.com/careers/) | Official page now directs candidates to Palo Alto Networks because CyberArk is a Palo Alto Networks company. **Reject as duplicate coverage**, not a separate company ID. |
| 82 | AutoDS | [First-party Greenhouse board](https://job-boards.greenhouse.io/autods) | Board states AutoDS was acquired by Fiverr and now operates with Fiverr support. Current jobs are non-target commercial functions. **Hold for parent/subsidiary policy**, rather than silently double-counting Fiverr. |
| 83 | Decart | [First-party Ashby posting](https://jobs.ashbyhq.com/decart-ai/7aebcce2-0a43-4d1a-8f26-7acb529aebc7) | Search-visible Tel Aviv postings exist, but all plausible public Ashby board tokens (`decart`, `decartai`, `decart-ai`) returned 404 live. **Hold until the canonical listing endpoint is found**. |
| 84 | Mavens | [First-party Greenhouse board](https://job-boards.greenhouse.io/mavenscareers) | The public API currently returns zero jobs. **Hold — empty board**. |
| 85 | Aquant | [First-party Ashby board](https://jobs.ashbyhq.com/Aquant) | Live API returns 3 jobs and none are in Israel. **Hold — no current Israel work**. |
| 86 | Walnut | [First-party Greenhouse API](https://boards-api.greenhouse.io/v1/boards/walnut/jobs?content=true) | Live board exists but returns zero jobs. **Hold — empty board**. |
| 87 | OpenWeb | [First-party Greenhouse API](https://boards-api.greenhouse.io/v1/boards/openweb/jobs?content=true) | Live board exists but returns zero jobs. **Hold — empty board**. |
| 88 | Bjak / A1 | [First-party Ashby posting](https://jobs.ashbyhq.com/bjakcareer/a798dd4c-6983-4274-8be7-a7e2f65c2027) | A remote Israel role is published under Bjak’s board but describes a product called A1. **Hold — employer/brand identity is ambiguous**, and the catalog should not invent a company mapping. |

## Summary for root-agent activation

- The discovery pass initially marked **43 candidates as promote-ready**.
  Production-path verification later rejected Dream as duplicate coverage,
  GitLab and MedOne for zero strict-location matches, and REAL pending a
  canonical identity decision. That left 39 from the original shortlist.
- **45 additional fresh candidates** were investigated and dispositioned as
  adapter verification or deliberate holds.
- Highest-value early-career signals in the ready set include Upstream's
  student Data Analyst, Guardio's entry-level IT role, Landa's student roles,
  and Rapid Medical's entry-level role.
- Canonical/ownership decisions called out explicitly: Sentra's dual ATS,
  Chainalysis/Alterya, CyberArk/Palo Alto Networks, AutoDS/Fiverr and
  Astrix/Cisco.
- No Taleo or other unsupported ATS was force-fit into an existing mapping.

Before editing `companies.json`, run every promote candidate through
`fetch_jobs_from_company()` and record status, job count, unique ID count,
empty title/location rate, and at least one production-recognized Israeli
location. The raw endpoint checks above establish the discovery baseline, not
the final activation guarantee.

## Final production verification and activation

The root agent exercised every finalist through
`scrapers.orchestrator.fetch_jobs_from_company()` and then evaluated every
returned job with `LocationFilter(strict_mode=True)`. The verification recorded
typed status, raw job count, unique ID count, empty title/location counts,
strict Israel count, sample locations, and elapsed time. The original 50
routes returned `SUCCESS`, at least one strict Israel match, unique IDs for
every returned job, and no empty titles. A later catalog-relevance audit
deactivated Tenengroup because none of those jobs matched the target-role
vocabulary, leaving 49 active additions. Plaee had one non-Israel job with an
empty location; its other nine jobs had explicit Bnei Brak / Ramat Gan data.

Eleven additional candidates found during the root-agent endpoint audit replaced
the four rejected original finalists and brought the batch to the requested 50:

| Company | First-party endpoint | Production result | Final disposition |
|---|---|---:|---|
| April | [Ashby API](https://api.ashbyhq.com/posting-api/job-board/april) | 14 jobs / 4 Israel | **Activated**. |
| Beach Bum | [Ashby API](https://api.ashbyhq.com/posting-api/job-board/beach-bum) | 3 / 3 | **Activated**. |
| Cloudinary | [Lever API](https://api.lever.co/v0/postings/cloudinary?mode=json) | 8 / 4 | **Activated**. |
| Connecteam | [Greenhouse API](https://boards-api.greenhouse.io/v1/boards/connecteam/jobs?content=true) | 57 / 19 | **Activated**. |
| DoiT | [Greenhouse API](https://boards-api.greenhouse.io/v1/boards/doitintl/jobs?content=true) | 122 / 13 | **Activated**. |
| Electreon | [Greenhouse API](https://boards-api.greenhouse.io/v1/boards/electreon/jobs?content=true) | 5 / 2 | **Activated**. |
| Loora | [Ashby API](https://api.ashbyhq.com/posting-api/job-board/loora) | 7 / 7 | **Activated**. |
| Capitolis | [Greenhouse API](https://boards-api.greenhouse.io/v1/boards/capitolis/jobs?content=true) | 2 / 1 | **Activated**. |
| Retym | [Comeet board](https://www.comeet.com/jobs/retym/C6.003) | 35 / 15 | **Activated**. |
| Majestic Labs | [Comeet board](https://www.comeet.com/jobs/majesticlabs/AA.004) | 33 / 16 | **Activated**. |
| Shield | [Comeet board](https://www.comeet.com/jobs/shieldfc/A5.00E) | 9 / 2 | **Activated**. |

Post-audit active ATS mix (49 total; Tenengroup remains as an inactive audit
record):

- 22 Comeet: Buildots, Vi, Automat-it, Sentra, Tastewise, Shopic, CHEQ,
  Guardio, Zenity, Upstream Security, Orchid Security, Onyx Security,
  Surecomp, Rapid Medical, Landa Digital Printing, AT&T Israel, BlinkOps,
  Finubit, Plaee, Retym, Majestic Labs, and Shield.
- 15 Greenhouse: Innovid, BeamUP, Credible, Nift, Guidde, Unframe,
  Honeycomb Insurance, Sweet Security, Obligo, Oasis Security, Conifers.ai,
  Connecteam, DoiT, Electreon, and Capitolis.
- 8 Ashby: Unit, Chainalysis, Nexxen, Airwallex, Viz.ai, April, Beach Bum,
  and Loora.
- 3 Workable: Autofleet, Tomax, and Nuvei.
- 1 Lever: Cloudinary.

Canonical and ownership decisions from the final gate:

- Sentra's Comeet board returned 12 jobs / 8 Israel, while its alternate Ashby
  board returned only 3 jobs / 0 Israel. Only Comeet was activated.
- Chainalysis includes its Alterya team; no separate Alterya record was added.
- Dream's exact Comeet URL already belonged to the existing `dream_security`
  record, so no duplicate was added.
- GitLab and MedOne were not activated because their production-normalized
  locations produced zero Israel matches.
- REAL stayed on hold because its generic brand/domain identity remains
  ambiguous even though its Workable feed contains Tel Aviv jobs.
- Tenengroup was deactivated after the new target-role gate found zero
  software/data/product/security roles despite a healthy Comeet integration.

## Additional endpoint probes performed during final verification

The final gate also ran conservative first-party careers-page signature checks
and public Greenhouse/Ashby/Lever token probes. These were discovery probes, not
evidence for activation; guessed tokens were never written to the catalog.

Confirmed public boards that were not activated because they had no current
production-recognized Israel jobs (or were empty) were Bright Machines
(Lever, 16/0), Constructor (Ashby, 43/0), Contentsquare (Lever, 34/0), Endor
Labs (Greenhouse, 29/0), Outreach (Lever, 31/0), Clarity (Ashby, 4/0), Walnut
(Greenhouse, 0 jobs), and the alternate Sentra Ashby board (3/0). Shield's
unrelated Greenhouse board had one non-Israel job; the canonical Shield
Financial Comeet board was activated instead. ZoomInfo's raw payload contained
Israel text only inside unrelated job content; its normalized locations did not
establish a current Israel role, so it was not activated.

The following official careers pages exposed a real ATS signature, but were
left for a later batch because a current Israeli sample and canonical board
could not both be completed through the production path in this pass: Fordefi
(Ashby), MIND, Evinced, Utila, StarkWare, Quris AI, Feedvisor, Nagomi Security,
Orca AI, Riverside, Explorium, NextSilicon, BeeHero (Comeet), and Vayyar and
Anzu (Workable). Knostic also exposed Comeet but had no current openings.

Two automated probes rediscovered existing catalog coverage and were discarded:
Classiq and ThetaRay. `Vi Labs` was only a naming alias for the activated `Vi`
board, not a second employer.

The remaining names below were checked against plausible official careers
paths and/or public ATS tokens, but no stable supported canonical feed with a
current Israel job was established. Their disposition is **hold / verify in a
future batch**, not activation:

AI21 Labs; AIVF; Agora; Aim Security; Aleph Farms; Anchor; Anodot; Apex
Security; Aporia; Argus Cyber Security; Arnica; Aurora Labs; BionicHIVE;
Breeze; Bria; Caja Robotics; Candivore; Certora; Chargeflow; Civ Robotics;
Cognata; CogniFiber; CoreTigo; CropX; Cybellum; Cyberint; Cynet; Darrow; Datos
Health; DayTwo; Deepchecks; Deepdub; Demostack; Dig Security; Driivz; Eco Wave
Power; Embryonics; Enso Security; Fabric; Firefly; Flytrex; FundGuard; Gem
Security; GenCell; Gilat; Glassbox; Gomboc; Grip Security; GuardKnox; Hour One;
Hunters; Indoor Robotics; Jit Security; Lasso Security; LightSolver; LinearB;
Liquidity; Lumigo; MeMed; Mentee Robotics; Miggo Security; MineOS; Mona Labs;
Moovit; Nexite; Nilus; Novee Security; Nucleai; Nuvo; Oddity; Okoora; Onebeat;
Opus Security; Papaya Gaming; PayEm; Planck; Prompt Security; Quantum Source;
Ramon.Space; Rezonate; Satori; Scopio Labs; Seal Security; SeeTree; Sight
Diagnostics; Skyline Robotics; Sola Security; Speedata; Taranis; Tenzai;
Unity; Valence Security; Variscite; Vesttoo; Vimeo; Wing Security; XM Cyber;
Zesty; Zooz Power; aiOla; env0; lakeFS; and vcita.
