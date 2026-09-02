"""Pipeline tests. No network: sources are exercised against fixtures and
the LLM is replaced with a deterministic fake.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from tradewatch.digest import render_html, render_markdown
from tradewatch.llm import FakeLLM
from tradewatch.models import Category, Digest, DigestEntry, RawDocument, SourceType
from tradewatch.pipeline.relevance import assess, heuristic_category, prefilter
from tradewatch.pipeline.summarize import summarize
from tradewatch.sources.federal_register import FederalRegisterSource, parse_document
from tradewatch.sources.rss import FeedConfig, parse_feed
from tradewatch.store import Store

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fr_results() -> list[dict]:
    data = json.loads((FIXTURES / "federal_register_sample.json").read_text())
    return data["results"]


@pytest.fixture
def shrimp_doc(fr_results) -> RawDocument:
    doc = parse_document(fr_results[0])
    assert doc is not None
    return doc


# --- Source parsing -------------------------------------------------------


def test_parses_valid_federal_register_record(shrimp_doc: RawDocument):
    assert shrimp_doc.external_id == "2026-14822"
    assert shrimp_doc.published == date(2026, 7, 28)
    assert shrimp_doc.source is SourceType.FEDERAL_REGISTER
    assert "International Trade Administration" in shrimp_doc.agencies


def test_malformed_record_returns_none_instead_of_raising(fr_results):
    assert parse_document(fr_results[3]) is None


def test_agencies_handles_both_dict_and_string_forms(fr_results):
    doc = parse_document(fr_results[2])
    assert doc is not None
    assert doc.agencies == ["Commerce Department"]


def test_content_hash_is_stable_and_content_derived(shrimp_doc: RawDocument):
    twin = shrimp_doc.model_copy(update={"url": "https://different.example/x"})
    assert twin.content_hash == shrimp_doc.content_hash

    different = shrimp_doc.model_copy(update={"title": "Something else entirely"})
    assert different.content_hash != shrimp_doc.content_hash


def test_rss_parsing():
    feed = b"""<?xml version="1.0"?>
    <rss version="2.0"><channel><title>USTR</title>
      <item>
        <title>United States and India Conclude Trade Talks</title>
        <link>https://ustr.gov/releases/2026/india-talks</link>
        <description>Statement on the conclusion of negotiations.</description>
        <pubDate>Mon, 27 Jul 2026 14:00:00 GMT</pubDate>
      </item>
      <item><title>No link item</title></item>
    </channel></rss>"""
    config = FeedConfig(url="https://ustr.gov/rss.xml", source=SourceType.USTR, label="USTR")
    docs = parse_feed(feed, config)

    assert len(docs) == 1, "items without a link should be dropped"
    assert docs[0].published == date(2026, 7, 27)
    assert docs[0].source is SourceType.USTR


def test_rss_handles_garbage_input_without_raising():
    config = FeedConfig(url="https://x.test/f", source=SourceType.USTR, label="X")
    assert parse_feed(b"this is not xml at all", config) == []


def test_rss_strips_html_from_descriptions():
    """Page markup in <description> must not reach the digest or the filter."""
    feed = b"""<?xml version="1.0"?>
    <rss version="2.0"><channel><title>USTR</title>
      <item>
        <title>Virginia</title>
        <link>https://ustr.gov/countries-regions/virginia</link>
        <description>&lt;span class="field field--name-uid"&gt;Exports to
        India rose&lt;/span&gt; &amp;amp; steel led the way.</description>
        <pubDate>Tue, 28 Jul 2026 15:42:28 GMT</pubDate>
      </item>
    </channel></rss>"""
    config = FeedConfig(url="https://ustr.gov/rss.xml", source=SourceType.USTR, label="USTR")
    doc = parse_feed(feed, config)[0]

    assert "<span" not in doc.abstract
    assert "field--name-uid" not in doc.abstract
    assert "Exports to India rose" in doc.abstract
    assert "&" in doc.abstract, "entities should be unescaped, not dropped"


def test_feed_label_does_not_leak_into_prefilter_text():
    """A feed label must not put its own words into every document.

    `agencies` feeds searchable_text(), so a label like "PIB India releases"
    made every item from that feed match the India prefilter and earn a
    model call — the prefilter's whole job, defeated by a display string.
    """
    feed = b"""<?xml version="1.0"?>
    <rss version="2.0"><channel><title>PIB</title>
      <item>
        <title>Minister inaugurates regional handicrafts exhibition</title>
        <link>https://pib.gov.in/release/12345</link>
        <description>An exhibition of regional crafts opened today.</description>
        <pubDate>Mon, 27 Jul 2026 14:00:00 GMT</pubDate>
      </item>
    </channel></rss>"""
    config = FeedConfig(
        url="https://pib.gov.in/rss", source=SourceType.PIB, label="PIB India releases"
    )
    docs = parse_feed(feed, config)

    assert len(docs) == 1
    assert "india" not in docs[0].searchable_text()
    assert prefilter(docs[0]) is False, "label words must not force a model call"


# --- Federal Register fetching --------------------------------------------


def _fr_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_fetch_follows_pagination(fr_results):
    """per_page is a page size, not a result cap — later pages must be read."""
    pages = {
        1: {"total_pages": 2, "results": [fr_results[0]]},
        2: {"total_pages": 2, "results": [fr_results[1]]},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params.get("page", 1))
        return httpx.Response(200, json=pages[page])

    async with _fr_client(handler) as client:
        source = FederalRegisterSource(client, per_page=1)
        docs = await source.fetch(since=date(2026, 7, 1), terms=["India"])

    assert len(docs) == 2, "second page was dropped"


@pytest.mark.asyncio
async def test_fetch_stops_at_the_page_cap(fr_results):
    """A source that always claims more pages must not loop forever."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"total_pages": 9999, "results": [fr_results[0]]})

    async with _fr_client(handler) as client:
        source = FederalRegisterSource(client, per_page=1, max_pages=3)
        docs = await source.fetch(since=date(2026, 7, 1), terms=["India"])

    assert len(docs) == 1, "same document on every page collapses on document number"


@pytest.mark.asyncio
async def test_non_json_body_does_not_kill_the_other_terms(fr_results):
    """A 200 carrying an HTML error page used to abort the whole source."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("conditions[term]") == "tariff":
            return httpx.Response(200, text="<html>Service unavailable</html>")
        return httpx.Response(200, json={"total_pages": 1, "results": [fr_results[0]]})

    async with _fr_client(handler) as client:
        source = FederalRegisterSource(client)
        docs = await source.fetch(since=date(2026, 7, 1), terms=["India", "tariff"])

    assert len(docs) == 1, "the healthy term should still return its documents"


# --- Relevance ------------------------------------------------------------


def test_prefilter_keeps_india_documents(shrimp_doc: RawDocument):
    assert prefilter(shrimp_doc) is True


def test_prefilter_keeps_trade_relevant_doc_without_india(fr_results):
    doc = parse_document(fr_results[1])
    assert doc is not None
    assert prefilter(doc) is True, "export control + supply chain should survive"


def test_prefilter_drops_routine_administrative_notice(fr_results):
    doc = parse_document(fr_results[2])
    assert doc is not None
    assert prefilter(doc) is False


def test_prefilter_counts_one_concept_once(shrimp_doc: RawDocument):
    """Variants of a single concept must not add up to the two-term gate."""
    doc = shrimp_doc.model_copy(
        update={
            "title": "Procedural notice on antidumping and anti-dumping filings",
            "abstract": None,
            "agencies": [],
        }
    )
    assert prefilter(doc) is False, "two spellings of one term are one signal"


def test_prefilter_ignores_bare_import_export_mentions(shrimp_doc: RawDocument):
    doc = shrimp_doc.model_copy(
        update={
            "title": "Agency information collection: import and export data forms",
            "abstract": None,
            "agencies": [],
        }
    )
    assert prefilter(doc) is False, "bare import/export match nearly every notice"


def test_heuristic_category(shrimp_doc: RawDocument, fr_results):
    assert heuristic_category(shrimp_doc) is Category.AD_CVD
    export_doc = parse_document(fr_results[1])
    assert heuristic_category(export_doc) is Category.EXPORT_CONTROL


@pytest.mark.asyncio
async def test_assess_parses_model_json(shrimp_doc: RawDocument):
    llm = FakeLLM(
        json.dumps(
            {
                "is_relevant": True,
                "score": 0.92,
                "category": "ad_cvd",
                "reason": "Direct duty determination on Indian exports.",
            }
        )
    )
    verdict = await assess(shrimp_doc, llm)
    assert verdict.is_relevant is True
    assert verdict.category is Category.AD_CVD
    assert verdict.score == pytest.approx(0.92)


@pytest.mark.asyncio
async def test_assess_applies_threshold(shrimp_doc: RawDocument):
    llm = FakeLLM(json.dumps({"is_relevant": True, "score": 0.2, "category": "other"}))
    verdict = await assess(shrimp_doc, llm, threshold=0.55)
    assert verdict.is_relevant is False, "low score must override the model's flag"


@pytest.mark.asyncio
async def test_assess_survives_non_json_response(shrimp_doc: RawDocument):
    llm = FakeLLM("Sure! Here's my assessment: this looks relevant.")
    verdict = await assess(shrimp_doc, llm)
    assert verdict.reason == "parse_failed"
    assert verdict.category is Category.AD_CVD, "falls back to heuristic"


@pytest.mark.asyncio
async def test_parse_failure_is_exempt_from_the_threshold(shrimp_doc: RawDocument):
    """The 0.5 placeholder sits below the 0.55 default cutoff, so applying
    the threshold to it would silently drop every unparseable response.
    """
    llm = FakeLLM("I'm not going to answer in JSON, sorry.")
    verdict = await assess(shrimp_doc, llm, threshold=0.55)
    assert verdict.is_relevant is True, "unparseable responses must reach a human"

    strict = await assess(shrimp_doc, llm, threshold=0.95)
    assert strict.is_relevant is True, "even a strict threshold must not drop it"


@pytest.mark.asyncio
async def test_assess_tolerates_preamble_before_json(shrimp_doc: RawDocument):
    llm = FakeLLM(
        'Here is the assessment you asked for:\n'
        '{"is_relevant": true, "score": 0.77, "category": "tariff"}\n'
        'Let me know if you need more detail.'
    )
    verdict = await assess(shrimp_doc, llm)
    assert verdict.category is Category.TARIFF
    assert verdict.reason != "parse_failed"
    assert verdict.score == pytest.approx(0.77)


@pytest.mark.asyncio
async def test_assess_handles_fenced_json(shrimp_doc: RawDocument):
    llm = FakeLLM('```json\n{"is_relevant": true, "score": 0.8, "category": "tariff"}\n```')
    verdict = await assess(shrimp_doc, llm)
    assert verdict.category is Category.TARIFF


# --- Summarization --------------------------------------------------------


@pytest.mark.asyncio
async def test_summarize_produces_briefing(shrimp_doc: RawDocument):
    llm = FakeLLM(
        json.dumps(
            {
                "headline": "Commerce finalises shrimp dumping margins for Indian exporters",
                "context": "Annual administrative review of a long-standing order.",
                "key_points": ["Final results issued", "Rates vary by exporter"],
                "india_impact": "Affects Andhra Pradesh and Odisha shrimp exporters.",
                "category": "ad_cvd",
                "significance": 3,
                "affected_sectors": ["seafood"],
            }
        )
    )
    briefing = await summarize(shrimp_doc, llm)
    assert briefing.significance == 3
    assert briefing.category is Category.AD_CVD
    assert briefing.document_hash == shrimp_doc.content_hash


@pytest.mark.asyncio
async def test_summarize_falls_back_on_bad_json(shrimp_doc: RawDocument):
    briefing = await summarize(shrimp_doc, FakeLLM("not json"))
    assert "Not assessed" in briefing.india_impact
    assert briefing.significance == 1
    assert briefing.category is Category.AD_CVD


@pytest.mark.asyncio
async def test_summarize_clamps_out_of_range_significance(shrimp_doc: RawDocument):
    llm = FakeLLM(
        json.dumps(
            {
                "headline": "x",
                "context": "y",
                "key_points": ["z"],
                "india_impact": "w",
                "category": "tariff",
                "significance": 99,
            }
        )
    )
    briefing = await summarize(shrimp_doc, llm)
    assert briefing.significance == 5


# --- Store ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_store_roundtrip_and_idempotency(tmp_path, shrimp_doc: RawDocument):
    store = Store(tmp_path / "t.db")
    llm = FakeLLM(
        json.dumps(
            {
                "headline": "Shrimp duty review finalised",
                "context": "c",
                "key_points": ["p"],
                "india_impact": "i",
                "category": "ad_cvd",
                "significance": 4,
                "affected_sectors": ["seafood"],
            }
        )
    )
    briefing = await summarize(shrimp_doc, llm)

    for _ in range(2):
        store.save_document(shrimp_doc)
        store.save_briefing(briefing)

    entries = store.entries_for(date.today())
    assert len(entries) == 1, "re-saving must not duplicate"
    assert entries[0].briefing.significance == 4
    assert shrimp_doc.content_hash in store.seen_hashes()


# --- Rendering ------------------------------------------------------------


def _digest_with(entry: DigestEntry) -> Digest:
    return Digest(
        digest_date=date(2026, 7, 30),
        entries=[entry],
        documents_scanned=120,
        documents_filtered=119,
    )


@pytest.mark.asyncio
async def test_renderers_include_impact_and_source(shrimp_doc: RawDocument):
    llm = FakeLLM(
        json.dumps(
            {
                "headline": "Shrimp duty review finalised",
                "context": "Background here.",
                "key_points": ["First point"],
                "india_impact": "Affects Indian seafood exporters.",
                "category": "ad_cvd",
                "significance": 4,
                "affected_sectors": ["seafood"],
            }
        )
    )
    briefing = await summarize(shrimp_doc, llm)
    digest = _digest_with(DigestEntry(document=shrimp_doc, briefing=briefing))

    md = render_markdown(digest)
    assert "Affects Indian seafood exporters." in md
    assert shrimp_doc.url in md
    assert "Anti-Dumping" in md

    html = render_html(digest)
    assert "<html" in html
    assert "Impact on India" in html


def test_empty_digest_renders_cleanly():
    digest = Digest(
        digest_date=date(2026, 7, 30),
        entries=[],
        documents_scanned=40,
        documents_filtered=40,
    )
    assert "No relevant developments" in render_markdown(digest)
    assert "No relevant developments" in render_html(digest)
