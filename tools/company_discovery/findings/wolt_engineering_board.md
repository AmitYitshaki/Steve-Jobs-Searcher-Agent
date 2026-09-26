# Wolt engineering board audit

Research date: 2026-09-26. Evidence is limited to Wolt-owned careers pages
and Wolt's first-party Greenhouse boards/APIs.

## Question

Is the `woltisrael` Greenhouse board an appropriate source for Wolt
engineering/R&D jobs, and what is the canonical public source for Wolt's
technical openings?

## Live findings

### `woltisrael` is an Israel-local non-technical board

The [`woltisrael` Greenhouse API](https://boards-api.greenhouse.io/v1/boards/woltisrael/jobs?content=true)
returned 56 live jobs. All 56 were located in Israel, but none belonged to an
Engineering, R&D, or Data department and none had an engineering-like title.
The only departments represented were Country Support, Order Fulfillment,
Order Fulfillment Management, and Wolt Market Country Admin.

The human-facing [`woltisrael` board](https://job-boards.greenhouse.io/woltisrael)
confirms the same shape: warehouse pickers, inventory staff, shift
supervisors, store work, and administrative/support roles. It is therefore
slightly more precise to call it an **operations/support/store/admin board**
than literally "operations-only," but it is not an engineering or R&D feed.

### The global `wolt` board is the canonical technical feed

The global [`wolt` Greenhouse API](https://boards-api.greenhouse.io/v1/boards/wolt/jobs?content=true)
returned 213 live jobs. It contained the current Engineering/R&D/Data jobs,
including 15 engineering-like roles in the live title/department audit. The
human-facing source is the [`wolt` Greenhouse board](https://job-boards.greenhouse.io/wolt).

Wolt's own [Engineering-filtered careers page](https://careers.wolt.com/en/jobs?team=Engineering)
showed 14 current engineering jobs and linked them using the same Greenhouse
job IDs, demonstrating that Wolt's branded careers site mirrors the global
`wolt` board rather than `woltisrael` for technical hiring.

A concrete live example is [FullStack Engineer, job 8176407](https://job-boards.greenhouse.io/wolt/jobs/8176407)
in Tallinn. The posting includes React and TypeScript responsibilities and
Node.js/Python as desirable experience. Wolt exposes the same role under the
same ID on its [official careers-site mirror](https://careers.wolt.com/en/jobs/1/8176407).

### Current Israel engineering availability

At this snapshot, the global `wolt` feed contained 11 jobs whose normalized
location was in Israel, but none was an Engineering/R&D/Data role. The Israel
roles were sales, advertising, operations, trust-and-safety, or store-related.
Consequently, there is no live Israeli technical job to use as a truthful
sample today; substituting a non-technical Israel role would misrepresent the
feed.

## Recommendation

For a catalog intended to discover software, data, product, and other
technical work, use the global Greenhouse board token **`wolt`**, not
`woltisrael`:

`https://boards-api.greenhouse.io/v1/boards/wolt/jobs?content=true`

Keep the normal strict Israel location filter. It will currently yield
`NO_JOBS`, which is the correct result: Wolt has an active canonical
engineering feed, but no verified Israeli engineering opening at the time of
this audit. Do not activate `woltisrael` as a substitute, because doing so
would ingest a large set of warehouse, store, support, and administrative jobs
without improving technical-job coverage.

