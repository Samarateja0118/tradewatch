# TradeWatch

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
