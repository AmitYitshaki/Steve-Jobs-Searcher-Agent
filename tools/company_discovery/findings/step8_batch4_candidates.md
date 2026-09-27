# Step 8 batch 4 candidate findings

Date: 2026-09-27

## Outcome

This final discovery pass activates 9 companies. Each activation passed the
four required gates against live first-party data: a current official careers
surface, an ATS identity established from that surface, at least one current
Israel job, and at least one current title accepted by
`matches_target_role()` (seniority intentionally ignored for this gate).

All names, domains, and exact `api_url` values were checked against the
354-entry catalog at `941c20a`. No new entry shares an API URL with an existing
catalog record. The resulting catalog has 363 records, of which 357 are active.

Counts below are `all jobs / strict-Israel jobs / target-role jobs anywhere`.
The relevance gate is company-wide, so its matching title need not be the same
record that proves a current Israel presence.

## Activated

| Company (`company_id`) | ATS and primary evidence | Live counts | Evidence sample |
|---|---|---:|---|
| Playtika (`playtika`) | [Official careers page](https://www.playtika.com/position/) embeds Greenhouse board `playtikaltd`; [API](https://boards-api.greenhouse.io/v1/boards/playtikaltd/jobs?content=true) | 24 / 14 / 7 | `Data Science`, Israel |
| Tomorrow.io (`tomorrow_io`) | [Official careers page](https://www.tomorrow.io/careers/) contains its Greenhouse-board component; [API](https://boards-api.greenhouse.io/v1/boards/tomorrow/jobs?content=true) | 22 / 3 / 2 | `AI First DevOps Engineer`, Tel Aviv |
| Snowflake (`snowflake`) | [Official EMEA careers page](https://careers.snowflake.com/us/en/emea-jobs) links first-party Ashby postings; [API](https://api.ashbyhq.com/posting-api/job-board/snowflake) | 349 / 1 / 86 | Israel remote `Solutions Architect`; software roles establish relevance |
| Earnix (`earnix`) | [Official Israel careers page](https://earnix.com/our-story/careers/israel/) exposes Comeet UID `93.00B`; [board](https://www.comeet.com/jobs/earnix/93.00B) | 13 / 3 / 4 | `Data Scientist - AI Research`, Ramat Gan |
| Riverside (`riverside`) | [Official careers site](https://careers.riverside.com/) and canonical Comeet UID `66.009`; [board](https://www.comeet.com/jobs/riverside-fm/66.009) | 23 / 14 / 5 | `DevOps Engineer`, Tel Aviv |
| Scytale (`scytale`) | [Official careers source](https://scytale.ai/scytale-careers/) embeds Comeet UID `2A.009`; [board](https://www.comeet.com/jobs/scytale/2A.009) | 18 / 1 / 5 | Tel Aviv `Product Manager`; engineering roles establish relevance |
| Nova (`nova`) | [Official Israel careers page](https://nova.co.il/location_filter/israel/) exposes Comeet UID `A5.007`; [board](https://www.comeet.com/jobs/nova/A5.007) | 96 / 33 / 4 | `Deep Learning Researcher`, Rehovot |
| Nanox (`nanox`) | [Official careers source](https://www.nanox.vision/careers/) embeds Comeet UID `43.00F`; [board](https://www.comeet.com/jobs/nanox/43.00F) | 6 / 5 / 3 | `Junior Software Developer`, Petah Tikva |
| Minute Media (`minute_media`) | [Official careers source](https://www.minutegroup.com/company/careers/) links Comeet UID `45.00A`; [board](https://www.comeet.com/jobs/minute/45.00A) | 7 / 4 / 3 | `Full Stack Developer`, Tel Aviv |

ATS breakdown: 6 Comeet, 2 Greenhouse, and 1 Ashby.

## Held: no target-role job

| Company | Primary evidence | Live result and disposition |
|---|---|---|
| AudioCodes | [Official careers page](https://www.audiocodes.com/careers) embeds Comeet UID `85.004`; [board](https://www.comeet.com/jobs/audiocodes/85.004) | `SUCCESS`, 16 / 8 Israel / 0 target. Hold: relevance gate failed. |
| MDClone | [Official careers page](https://mdclone.com/about-mdclone/careers/) links Comeet UID `66.004`; [board](https://www.comeet.com/jobs/mdclone/66.004) | `SUCCESS`, 3 / 1 / 0. Hold: relevance gate failed. |
| Evinced | [Official careers page](https://evinced.com/careers) exposes Comeet UID `28.000` | `SUCCESS`, 6 / 1 / 0. Hold: relevance gate failed. |

## Held: no current production-recognized Israel job

| Company | Evidence | Disposition |
|---|---|---|
| Trullion | [Official careers source](https://trullion.com/careers/) embeds Comeet UID `07.000`; [board](https://www.comeet.com/jobs/trullion/07.000) | 3 jobs, 0 Israel, 0 target. Hold: no Israel job. |
| Personetics | [Official careers source](https://personetics.com/careers/) embeds Comeet UID `83.00A`; [board](https://www.comeet.com/jobs/personetics/83.00A) | 12 jobs include three Israel target roles, but production strict filtering rejects them because the canonical job URLs use `/us/careers/`, which is interpreted as the blocked `US` location signal before the Israel metadata. Hold: runtime location collision; do not activate a feed that the pipeline cannot deliver correctly. |
| NeuReality | [Official careers source](https://www.neureality.ai/careers/) embeds Comeet UID `89.002` | `NO_JOBS`. Hold: empty feed. |
| Chain Reaction | [Official careers source](https://chain-reaction.io/careers/) embeds Comeet UID `A6.00D` | `NO_JOBS`. Hold: empty feed. |
| Sola Security | [Official careers page](https://sola.security/careers/) | Page explicitly has no current opening. Hold: empty feed. |

## Held: canonical source, unsupported ATS, or employer ambiguity

| Candidate | First-party evidence | Specific disposition |
|---|---|---|
| Origin Technology | [Official careers page](https://www.originhq.com/careers) is live; a public Ashby board returned 10 jobs including an Israel security role | Hold: the employer page did not expose or link the Ashby surface, so canonical ownership was not proven. |
| Noma Security | [Official careers page](https://noma.security/careers) lists Tel Aviv technical roles | Hold: custom/undiscovered source; no supported ATS signature. |
| Apono | [Official careers page](https://www.apono.io/careers/) lists a TLV backend role | Hold: employer-owned WordPress AJAX feed, not a supported ATS. |
| StarkWare | [Official careers page](https://starkware.co/careers/) lists an Israel-remote security role | Hold: custom source; new extraction seam required. |
| Fordefi | [Official careers page](https://fordefi.com/careers) accepts CVs but has no canonical feed | Hold: no canonical ATS and possible Paxos parent/subsidiary overlap. |
| Radware | Official careers surface uses Taleo | Hold: unsupported ATS; requires a dedicated adapter. |
| Evoke | [Official parent careers page](https://www.evokeplc.com/careers/) links several brand-specific careers surfaces | Hold: the Comeet board could not be tied to one canonical first-party source without parent/brand ambiguity. |
| OrCam | Official careers URL redirects to a generic recruiting surface | Hold: canonical employer feed not established. |
| AI21 Labs | Official careers route entered a redirect loop during verification | Hold: live canonical surface could not be verified. |
| Nayax | Official careers page returned 403 during research | Hold: source/ATS could not be verified reliably. |
| Lili | Checked official careers URL returned 404 despite a discoverable Comeet token | Hold: gate 1 failed; no live official careers page. |
| Augmedics | Checked official careers URL returned 404 despite a discoverable Comeet token | Hold: gate 1 failed. |
| Diagnostic Robotics | Checked official careers URL returned 404 | Hold: gate 1 failed. |
| Sweetch | Checked official careers URL returned 404 | Hold: gate 1 failed. |
| Highcon | Official site was suspended/unavailable | Hold: gate 1 failed. |
| DustPhotonics | Official route redirects to Credo after acquisition | Hold: acquired-company/parent overlap; do not create a second employer identity. |
| SatixFy | Official route redirects to MDA after acquisition | Hold: acquired-company/parent overlap. |

## Held: no supported canonical feed established in this pass

The following live employer-owned pages were inspected but did not expose a
supported, production-verifiable ATS feed. They remain distinct
`held: unsupported/ambiguous source` findings, not claims that the companies
have no jobs:

- StoreDot, Freightos, Pecan AI, Trigo, Growthspace, Anecdotes, OneLayer,
  TytoCare, Binah.ai, Medisafe, Cymbio, XSight Labs, Inuitive, XTEND,
  NextVision, UVision, H2Pro, Nano Dimension, and Massivit.
- `Electreon` appeared during discovery but was discarded immediately because
  it is already in the catalog; it was not researched as a new activation.

## Verification and duplicate notes

- Live counts came from `fetch_jobs_from_company()` using the production ATS
  adapters. Israel counts used `LocationFilter(strict_mode=True)`, and the
  fourth gate used the repository's `matches_target_role()` implementation.
- Search results were discovery aids only. ATS identity and canonical board
  decisions were grounded in employer-owned source or links.
- Exact API URL checks found no collision among the 9 activations and the
  existing catalog. No portfolio aggregator was activated.
- No location alias was added: every activated candidate is already recognized
  by the shared location vocabulary.
- The Personetics `/us/careers/` collision is documented for later repair; no
  adapter or filter code was changed inside this catalog-only batch.
