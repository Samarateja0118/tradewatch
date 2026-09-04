# TradeWatch

[![CI](https://github.com/Samarateja0118/tradewatch/actions/workflows/ci.yml/badge.svg)](https://github.com/Samarateja0118/tradewatch/actions/workflows/ci.yml)

An autonomous agent that monitors US government publications for developments
affecting India–US trade and technology relations, and produces a daily
structured briefing.

Built because reading the Federal Register, USTR releases and Commerce
announcements manually is a job nobody has time to do daily — but missing an
anti-dumping determination by a week has real consequences for exporters.

## What it does

Each run:

1. **Ingests** from the Federal Register API (every AD/CVD determination,
   tariff proclamation and export control rule is published there on the day
   it takes legal effect) and from RSS feeds for USTR, Commerce and PIB India.
2. **Filters** in two stages — a deterministic keyword prefilter, then an LLM
   relevance assessment on survivors.
3. **Extracts** a structured briefing per relevant document: context, key
   points, impact on India, significance rating, affected sectors.
4. **Stores** results in SQLite, keyed on a content hash so re-runs never
   re-summarize the same document.
5. **Renders** a markdown and HTML digest, sorted by significance.

## Architecture

```
sources/          →  pipeline/          →  store.py  →  digest.py
federal_register     relevance (2-stage)    SQLite      markdown
rss                  summarize (LLM)                    HTML
```

Design decisions worth noting:

**Two-stage filtering is the main cost lever.** The Federal Register publishes
hundreds of documents daily. Sending all of them to an LLM would be slow and
expensive for no gain. The deterministic prefilter drops the bulk of them at
zero marginal cost; only survivors get a model call. The gate requires two
*distinct* trade or tech concepts, counting spelling variants and inflections
of one concept once — otherwise "antidumping / anti-dumping" in a procedural
notice clears the bar on its own. The retention rate has not been measured
against a real day's fetch; the run log reports the counts needed to do so.

**Content-hash deduplication, not URL.** The same USTR release republished by
two sources should collapse to one entry. Hashing title + date + abstract
achieves that; hashing the URL would not.

**Every stage degrades rather than fails.** A malformed API record is skipped,
not raised. A model returning non-JSON falls back to a heuristic category. A
source that fails entirely is logged and the run continues on the others. One
bad document must not kill a day's digest.

**The briefing schema mirrors a government briefing note** — context, key
points, impact assessment, significance — rather than a generic summary. That
structure is what makes output usable for decisions rather than just readable.

**LLM access sits behind a narrow protocol.** The pipeline depends on a
one-method `LLMClient` interface, so the full pipeline is testable with a
deterministic fake and the provider can be swapped without touching pipeline
code.

## Setup

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-...
python -m tradewatch.main --days 1 --out ./briefs
```

Options: `--days` lookback window, `--threshold` relevance cutoff (0–1),
`--db` SQLite path, `--verbose`.

Scheduling — cron for a 7am daily run:

```
0 7 * * * cd /path/to/tradewatch && /usr/bin/python3 -m tradewatch.main >> run.log 2>&1
```

## Tests

```bash
python -m pytest tests/ -q
```

27 tests, no network required. Sources are exercised against fixtures and an
`httpx.MockTransport`; the LLM is replaced with a deterministic fake.
Coverage includes malformed API records, non-JSON model responses, fenced
JSON, prose wrapped around JSON, out-of-range values, pagination and the page
cap, a source returning a non-JSON body, store idempotency, and empty-digest
rendering.

## Status — what is and isn't verified

**Verified:** parsing, filtering, summarization, storage idempotency and
rendering, all under test against fixtures — 27 tests, all passing. A full
pipeline dry run has been executed end to end against an `httpx.MockTransport`
and a fake LLM: ingest → dedupe → prefilter → assess → summarize → store →
render, including a re-run over the same documents that produced zero new
model calls, confirming the content-hash dedup holds.

**Verified live (2026-08-04):** the Federal Register client runs against the
real API — payload shape, pagination, date filtering and parsing all match.
A three-day window returned 18 unique documents across the five search terms,
of which the prefilter kept 5 (72% dropped). That is the first real
measurement of the retention rate; the earlier "80–90%" figure was an
estimate and the true number depends on the window, since the API-level
search terms already narrow the set before the prefilter sees it.

Feed URLs were checked individually. Only USTR is usable — see the notes in
`sources/rss.py` for what was rejected and why (Commerce sits behind a
bot-detection challenge; the PIB feed is Hindi-only). The USTR feed itself is
thin and contributed nothing in the sample window.

**Not yet verified:** live Anthropic API calls. Everything up to the model
boundary has now been exercised against real endpoints; the relevance and
summarization stages have only ever run against the fake LLM.

Run once manually with `--verbose` before scheduling anything.

## Possible extensions

- MCP server wrapper so the corpus is queryable conversationally
- Embedding-based relevance instead of keyword prefilter, with a labelled
  evaluation set to measure precision/recall against the current approach
- Entity extraction for company and HTS-code level tracking
- Email delivery, or a FastAPI read layer with a small frontend

## Dashboard

A read-only web dashboard sits over the same SQLite file the pipeline writes.

```
pipeline (unchanged)  ->  SQLite  ->  read API (FastAPI)  ->  frontend (React + TS)
```

Three layers with a seam between each, and the seams are the point. The
pipeline is untouched — the dashboard is a reader of a system it does not own.
The API turns rows into JSON and holds no business logic: no thresholds, no
scoring, no reclassification. The frontend formats for display and computes
nothing the API could have sent.

The rule that keeps it that way: if something wants computing in the frontend
it probably belongs in the API, and if it wants computing in the API it
probably belongs in the pipeline.

### API

```
GET /api/documents?category=<slug>&min_significance=<1-5>&limit=50&offset=0
                                                        -> { items, total }
GET /api/documents/{id}                                 -> full briefing
GET /api/categories                                     -> [{ slug, label, count }]
```

Results are ordered by significance descending, matching the digest's own
ordering — a briefing tool should open on the most consequential thing, and that
is a product decision rather than a property of the column. `min_significance`
is a **floor, not an equality match**: "show me anything that matters" is the
question a reader has, and an exact filter would hide the 5s from someone asking
for 3.

A list carries metadata and the briefing headline; the note itself only comes
back from the detail endpoint. List views do not render the body, and shipping
it would multiply the payload for text nobody reads until they click.

Two properties worth naming. The connection opens in SQLite's **read-only
mode**, so the dashboard cannot write to the pipeline's database even by
accident — and a test asserts that `DELETE` raises rather than trusting the
comment above it. That is the same instinct as the `break-guardrails` harness in
[access-ai-gateway](https://github.com/Samarateja0118/access-ai-gateway), which
switches each defence off and records what gets through: a claim about a safety
property is worth what its demonstration is worth, and both projects would
rather run the failure than describe it.

And documents the prefilter rejected stay invisible: the table holds them, but
showing them would put work-in-progress in front of a reader expecting findings.

**There is no `confidence` field.** The relevance score is computed during
classification and never persisted, so the API cannot report it without the
pipeline changing. `significance` (1-5) is what is stored, and what orders a
list.

### Deployment

The API ships its own data. Nothing writes to the database at runtime, which
means it is not state — it is a **static asset that happens to be in SQLite
format**, and `data/snapshot.db` is committed and copied into the image.

That collapses the usual problem. No persistent volume, no scheduled job, no
`ANTHROPIC_API_KEY` at runtime, and ephemeral disk stops mattering because the
data is rebuilt from the repo on every deploy. Any free tier that takes a
Dockerfile will do.

It also keeps the three-layer architecture intact. Exporting static JSON and
serving the frontend alone would ship the same pixels, but it would throw away
the layer where the read-only enforcement and the contract decisions live —
which is the part worth showing.

*Future work:* a scheduled GitHub Action could run the pipeline weekly with the
key in secrets, commit the refreshed snapshot, and trigger a redeploy. That
buys freshness without giving the runtime any state to keep.

### Running it

```bash
pip install -r requirements.txt
uvicorn api.app:app --reload         # :8000, serves data/snapshot.db out of the box

cd frontend && npm install && npm run dev   # :5173
```

A fresh clone needs no setup: the API falls back to the committed snapshot, and
prefers `./tradewatch.db` when a real run has produced one, so a developer who
has just run the pipeline sees their own data without configuring anything.

`scripts/seed_demo.py` regenerates the snapshot offline, deterministically, with
no API key. It writes through `Store`, so its rows have the shape a real run
produces rather than one that merely looks similar.

```bash
python -m scripts.seed_demo --db data/snapshot.db   # rebuild the shipped snapshot
```

Frontend configuration is one variable, `VITE_API_URL`, so local and deployed
differ by environment rather than by code. The API's `TRADEWATCH_ALLOWED_ORIGINS`
has to name the deployed frontend or the browser will refuse the response.

### Frontend

Three pieces of state live in `App` — the two filters and the selected document
id — because each is set by one component and read by a sibling that cannot see
it. Everything below is presentational and takes props. There is no
Redux or Zustand: nothing is shared across distant branches, and a store would
add indirection without removing any.

Data fetching is `useEffect` + `fetch` behind a hook returning
`{ data, loading, error }`, all three always present, so a consumer that forgets
a state has an obviously missing branch rather than a blank screen. TanStack
Query would be defensible, but its benefits — dedup, caching,
stale-while-revalidate — answer problems three read-only endpoints do not have.

Errors are normalised in `api/client.ts`, so no component ever sees a raw fetch
rejection: a dropped connection, a 404 and a 500 all arrive as a typed `ApiError`
with a `kind` the UI switches on. Same instinct as the retries and circuit
breaking in the pipeline's HTTP layer, one level up.

Both filters are applied server-side. Filtering the fetched array in the browser
would narrow one page rather than the result set — indistinguishable on seven
documents and wrong on seven hundred.

Tests mock the API client rather than `fetch`, which keeps them tied to the
contract instead of the transport — the same reason the pipeline's tests use a
deterministic fake LLM client.

```bash
cd frontend && npm test        # component and state tests
pytest tests/test_api.py       # the API against a database Store wrote
```
