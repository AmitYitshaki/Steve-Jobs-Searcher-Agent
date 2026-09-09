# Group B: supported-ATS endpoint investigation — 9 September 2026

Research outcome: **8 verified job-data sources; 5 unresolved**. All 13 requested companies appear in `codex_20260909_group_b.csv`. “Solved” means live job records were personally fetched, **not** that the current adapter can consume the source unchanged. Important compatibility gaps are below. No production/configuration files or runtime state were modified; no Producer, AI, or Telegram calls ran.

Direct HTTP verification occurred at **2026-09-09 13:44:52–13:46:09 UTC**. Initial source-page fetches immediately preceded these. `codex_20260909_group_b_evidence.json` preserves safe request metadata, payloads, envelopes, counts, and sample job fields. It excludes cookies, session/CSRF values, recruiter names, and full descriptions. Counts describe the fetched scope, not guaranteed complete global coverage.

The existing discovery verifier was reused as a source of request conventions and headers; old findings were leads only. Fresh official HTML revealed three important earlier parser errors: Salt's `embed` path segment is not its board token; HP's `vs-errors` host is telemetry, not its employer board; Workday locale `en-US` must not be treated as a career-site identifier.

## Verified sources

### Salt Security — 12 jobs; existing Greenhouse mapping fits

[Official careers page](https://salt.security/careers) includes `https://boards.greenhouse.io/embed/job_board/js?for=saltsecurity`. GET [verified JSON endpoint](https://boards-api.greenhouse.io/v1/boards/saltsecurity/jobs?content=true) returned HTTP 200, root `jobs` array with 12 records. Samples: **Channel Account Manager**; **Channel Account Manager – Central**; **Controller - Part-Time (50%)**. The response has expected `id`, `title`, `location.name`, `absolute_url`, and `content`. Full returned board array, no pagination attempted/needed from this envelope. Geography is global and downstream location filtering remains necessary.

### ControlUp — 11 jobs; existing Lever mapping fits

[Official careers page](https://www.controlup.com/company/careers/) contains `window.leverJobsOptions = {accountName: 'controlup', includeCss: true}`. GET [verified endpoint](https://api.lever.co/v0/postings/controlup?mode=json) returned 11 records in a root array. Samples: **Commercial Account Executive – US West**; **DACH Enterprise Customer Success Manager**; **Devops Engineer**. `id`, `text`, `categories.location`, `hostedUrl`, and description fields fit the Lever mapping. Global board; no pagination signaled.

### Dell — 4 Israel-keyword jobs; ORC adapter fits with additional configuration

[Official board](https://enterpriseplatform.dell.com/hcmUI/CandidateExperience/en/sites/careers/jobs) explicitly declares `data-sitenumber="CX_1001"` and same-origin platform URLs. GET the [verified requisitions resource](https://enterpriseplatform.dell.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions) with query:

```text
onlyData=true
expand=requisitionList.secondaryLocations,requisitionList.workLocation
finder=findReqs;siteNumber=CX_1001,keyword=Israel,limit=25,offset=0
```

HTTP 200: `items[0].requisitionList` contained **4**, and `items[0].TotalJobsCount` was **4**. Samples: **Software Principal Engineer** (two distinct requisitions); **Technical Customer Success Manager**. The inspected examples have Herzliya, Tel Aviv, Israel as primary location. Initial request without `expand` returned metadata only, so expansion is essential.

Requires `oracle_site_number: "CX_1001"` and a reviewed `oracle_careers_url` prefix such as the observed site path plus `/job/`; job-detail navigation itself was not tested. The existing ORC adapter already constructs the exact expansion and finder. This is a complete returned keyword scope, not proof of worldwide coverage or perfect geographical recall.

### Sapiens — 2 Israel jobs; existing SuccessFactors parser fits

[Official homepage](https://careers.sapiens.com/) links `/search`. GET [verified Israel search](https://careers.sapiens.com/search/?q=&locationsearch=Israel) returned HTTP 200 with **2 `tr.data-row` records**: **Senior Finance Director**; **Revenue Controller**, both Holon, IL. Real `span.jobTitle` nested anchors were inspected, including `/job/Holon-Senior-Finance-Director/1415304233/`. The existing SuccessFactors adapter consumes this HTML shape without a separate JSON API. The count is rows on this response; global coverage was not investigated.

### Microchip Technology — 20 of 503 global jobs; current ID mapping needs repair

[Official Workday site supplied in the task](https://wd5.myworkdaysite.com/en-US/recruiting/microchiphr/External) returned HTTP 200 and explicitly declares `tenant: "microchiphr"`, `siteId: "External"`, and Workday `wd5` origin. POST [verified jobs endpoint](https://microchiphr.wd5.myworkdayjobs.com/wday/cxs/microchiphr/External/jobs):

```json
{"limit":20,"offset":0,"appliedFacets":{},"searchText":""}
```

HTTP 200, `jobPostings` **20**, `total` **503**. Samples: **Manufacturing Technician - Precision Electromechanical Assembly**; **Senior Engineer II - CAD (Physical Verification)**; **Senior Engineer II - Physical Design**. This is a **partial global first page**. The same payload with `searchText:"Israel"` returned a valid empty `jobPostings` array and `total:0`; that is an empty keyword search, not a broken endpoint. No Israel facet string was found in the returned global facets.

**Do not treat this as drop-in safe:** inspected records expose `title`, `externalPath`, `locationsText`, `postedOn`, and `bulletFields`; they do not expose `bulletinId` or `id`. The current mapping reads those missing ID fields, risking collisions/empty IDs. The first record's `bulletFields[0]` is `R1559-26` and its `externalPath` ends in the same requisition code. A stable-ID policy and proper human-facing base URL need review before activation. The endpoint itself is verified.

### Merck Life Science — 10 Israel jobs; Phenom payload and routing need adaptation

[Official search page](https://careers.emdgroup.com/us/en/search-results) declares `widgetApiEndpoint:"https://careers.emdgroup.com/widgets"`, locale `en_us`, country `us`, and page ID `page18`. POST [verified endpoint](https://careers.emdgroup.com/widgets):

```json
{"lang":"en_us","deviceType":"desktop","country":"us","pageName":"search-results","ddoKey":"refineSearch","from":0,"size":20,"jobs":true,"counts":true,"selected_fields":{"country":["Israel"]},"keywords":"","siteType":"external","pageId":"page18"}
```

HTTP 200, `refineSearch.data.jobs` **10**, `refineSearch.totalHits` **10**. Samples: **Principal Agentic AI Engineer**; **Senior Agentic AI Engineer**; **Principal Machine Learning Research Scientist**, all country Israel. Complete returned facet scope. This is the Merck/EMD group board and **does not isolate the Life Science division**.

The existing Thales-specific Phenom adapter is a useful parsing pattern, not a generic ready-made route: it hardcodes Thales locale/country and a Thales job-URL fallback. Reuse needs parameterization and verified detail-link construction when `applyUrl` is empty. No new adapter was written.

### Snowflake — 10 of 375 global embedded jobs; 1 Israel widget job

The supplied [Snowflake careers URL](https://www.snowflake.com/careers) redirects to [official Phenom careers](https://careers.snowflake.com/us/en). GET [verified search source used in CSV](https://careers.snowflake.com/us/en/search-results) returned embedded JSON at `phApp.ddo.eagerLoadRefineSearch.data.jobs`: **10** records, reported total **375**. Samples: **Sr Sales Development Representative**; **Sr. District Manager**; **Senior Solution Engineer**. Global first page only.

The page declares the widget URL and locale. POST [also verified widgets endpoint](https://careers.snowflake.com/widgets), same payload as Merck above but `pageId:"page11"`, returned **1 / totalHits 1** for country Israel: **Solutions Architect**. A single-record scope cannot supply 2–3 distinct sample titles; the CSV therefore uses the independently fetched global embedded-data source for its three samples.

Actual `applyUrl` values point to `https://jobs.ashbyhq.com/snowflake/<uuid>`; this is a strong first-party **Ashby backend lead**, but the Ashby posting API was **not requested or verified**. CSV `ats_type` describes the verified Phenom source. Existing generic ATS mapping does not consume this embedded Phenom JSON, and Thales-specific settings cannot simply be copied. Potential Ashby integration may ultimately be simpler, after a real request.

### eBay — 10 of 291 global embedded jobs; Israel widget query empty

GET [verified official search source](https://jobs.ebayinc.com/us/en/search-results) returned `phApp.ddo.eagerLoadRefineSearch.data.jobs`: **10** records, reported total **291**. Samples: **Category Management Associate FTC**; **Associate Tech Lead**; **Financial Controller, Certilogo**. Global first page only. This HTML source contains real structured job records; the CSV URL is **not a standalone JSON API**.

The page declares `https://jobs.ebayinc.com/widgets`. POST with the Merck payload adjusted to `pageId:"page15"` returned HTTP 200, `refineSearch.status:200`, `hits:0`, `totalHits:0`, and empty jobs for country Israel. The widget URL is not used in the CSV because that request alone returned no job records.

Observed job `applyUrl` values point to `https://ebay.wd5.myworkdayjobs.com/apply/job/...`; Workday tenant `ebay`, `wd5`, site `apply` is an explicit lead. The derived Workday API was **not requested or verified**. Phenom embedded-data support or a verified Workday route is required before activation.

## Unresolved companies

- **HP:** [official careers page](https://apply.hp.com/careers) HTTP 200 and genuine Eightfold assets/configuration. GET same-origin `/api/apply/v2/jobs` returned **403**, 39-byte JSON `message` envelope, no records. A browser capture of the actual public search call is still needed. The earlier `vs-errors.eightfold.ai` lead is not an employer board. This does not establish persistent WAF blocking or zero jobs.
- **Boston Scientific:** [official careers page](https://www.bostonscientific.com/en-US/careers.html) explicitly links [Eightfold board](https://bostonscientific.eightfold.ai/careers). Board HTTP 200; `/api/apply/v2/jobs` HTTP **403**, same small message envelope. The actual browser request was not captured. No conclusion about vacancies or permanent blocking.
- **Verint:** [official careers page](https://www.verint.com/careers/) explicitly links [Oracle tenant board](https://fa-epcb-saasfaprod1.fa.ocs.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX), which returned HTTP 200, document title Verint and `data-sitenumber="CX"`. No requisitions response was obtained. This is a high-quality lead, not a verified endpoint.
- **Vishay Intertechnology:** [official Israel page](https://jobs.vishay.com/locations/israel/) returned HTTP 200 but only **“One moment, please...”** challenge HTML with a periodic reload, no job links. No browser retry completed. Workday in the CSV is the task's prior classification, not a freshly observed working tenant. A single challenge does not justify a permanent `blocked` classification.
- **Fujitsu:** [official site](https://www.jobs.global.fujitsu.com/) has genuine SuccessFactors CDN references and `/search` links. Both Israel search and global search returned HTTP 200 but **zero `tr.data-row` records**. `j2w.searchResultsUnify.min.js` suggests a different rendering path. No real records or valid substitute selector confirmed. In particular, zero legacy rows does **not** mean zero worldwide jobs.

## Limits and next steps

Further network execution was stopped when automatic approval review rejected the next research request with a usage-limit error. The rejected action would have fetched Verint requisitions and global eBay/Snowflake widgets. It was not retried through another execution path. Browser work did not begin. Consequently, unresolved results are intentionally bounded observations, not claims that no endpoint exists.

Next highest-value checks: directly verify Snowflake's observed Ashby board and eBay's observed Workday board; fetch Verint ORC with site `CX`; capture HP/Boston's actual Eightfold request; inspect Fujitsu's rendered Unify result shape and retry Vishay in a browser. None of those unverified URLs has been placed in `api_url`.
