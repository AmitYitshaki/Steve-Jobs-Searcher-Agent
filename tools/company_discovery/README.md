# Company discovery — scaling companies.json

Working material for expanding `config/companies.json` from 68 to ~330
companies. This is not shipped application code; nothing here is imported
by `src/`.

## Files

- `candidates_all.json` — all 263 unique candidate companies (roster
  collected by ChatGPT across 6 batches), merged with what was recoverable
  after the consolidated spreadsheet lost most fields for 5 of the 6
  batches. Each entry has a `status`:
  - `ready_for_sniffing` — has a real `careers_url` to visit and inspect.
  - `needs_url_discovery` — only a company name survived; find the careers
    page before anything else.
- `batch_1.json` .. `batch_4.json` — `candidates_all.json` split into four
  ~66-company chunks, in original roster order, for incremental processing.
- `findings/` — per-batch verification results as each batch is worked
  through (ATS identified from page source, endpoint sniffed, sample job
  confirmed or not). Not created until a batch is processed.

## What "processing a batch" means

For each company: visit `careers_url` (or find one, if missing), identify
the real ATS from page source signatures (never from the URL shape alone —
that produced wrong guesses upstream), and where possible locate the actual
job-data endpoint. Nothing here writes to `config/companies.json` directly;
findings are reviewed before any entry is added there.

## Mandatory activation gates

A working ATS and an Israeli location are necessary but not sufficient. Before
activation, every candidate must pass all of these checks against real current
job data:

1. The employer is not already represented under another brand, subsidiary,
   parent, or alternate ATS feed.
2. The endpoint is the employer's canonical careers feed, not a warehouse,
   retail, staffing, portfolio, or other non-employer board.
3. At least one returned title matches `TARGET_ROLE_KEYWORDS` or
   `HEBREW_ROLE_KEYWORDS`, regardless of seniority. Run
   `python tools/company_discovery/relevance_gate.py <jobs.json>` against the
   saved verification payload. A non-zero exit means the company stays out.

Batch findings and reports must label failures of gate 3 separately as
`hold — no target-role jobs`; do not merge them into `zero jobs` or `ATS
ambiguity`. Batch size is an aspiration, never an activation criterion: fewer
qualified companies is the correct result when candidates fail these gates.
