"""Stage three: turn a relevant document into a structured briefing.

Like the relevance stage, this degrades rather than fails. A model that
returns something other than JSON yields a minimal briefing flagged as
unassessed, so the document still reaches the digest and a human still sees
it — it is not silently dropped.
"""

from __future__ import annotations

import json
import logging

from ..models import Briefing, Category, RawDocument
from .relevance import INDIA_TERMS, LLMClient, _term_hits, heuristic_category

log = logging.getLogger(__name__)

NOT_ASSESSED = "Not assessed — the model response could not be parsed."
NOT_ANALYSED = "[No model analysis — keyword listing only.]"

SUMMARIZE_SYSTEM = """You write briefing notes on US government documents \
for an audience tracking India-US trade and technology relations.

Respond with ONLY a JSON object, no prose and no markdown fences:
{
  "headline": "one line, under 100 characters",
  "context": "2-3 sentences of background a reader needs",
  "key_points": ["3-5 short factual points"],
  "india_impact": "concrete effect on Indian exporters, firms or policy",
  "category": "ad_cvd | tariff | ipr | export_control | trade_agreement | \
tech_policy | investment | other",
  "significance": 1-5,
  "affected_sectors": ["sectors touched, lowercase"]
}

significance: 5 is a major bilateral development, 3 is a routine \
determination affecting one sector, 1 is procedural. Be specific and factual; \
do not speculate beyond the document."""


def _extract_json_object(raw: str) -> str | None:
    """Pull the outermost JSON object out of a model response.

    Handles bare JSON, ```json fences, and the occasional preamble the model
    emits despite being told not to.
    """
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end <= start:
        return None
    return raw[start : end + 1]


def _fallback(doc: RawDocument) -> Briefing:
    """Minimal briefing used when the model response is unusable."""
    return Briefing(
        document_hash=doc.content_hash,
        headline=doc.title[:100],
        context=(doc.abstract or doc.title)[:500],
        key_points=[],
        india_impact=NOT_ASSESSED,
        category=heuristic_category(doc),
        significance=1,
        affected_sectors=[],
    )


def _coerce_briefing(raw: str, doc: RawDocument) -> Briefing:
    """Parse model output defensively; never let a bad response crash a run."""
    candidate = _extract_json_object(raw)
    if candidate is None:
        log.warning("Briefing response was not JSON for %s", doc.external_id)
        return _fallback(doc)

    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        log.warning("Briefing response was not JSON for %s", doc.external_id)
        return _fallback(doc)

    if not isinstance(data, dict):
        return _fallback(doc)

    try:
        category = Category(str(data.get("category", "other")).lower())
    except ValueError:
        category = heuristic_category(doc)

    try:
        significance = int(data.get("significance", 1))
    except (TypeError, ValueError):
        significance = 1

    key_points = data.get("key_points")
    sectors = data.get("affected_sectors")

    return Briefing(
        document_hash=doc.content_hash,
        headline=str(data.get("headline") or doc.title)[:200],
        context=str(data.get("context", "")),
        key_points=[str(p) for p in key_points] if isinstance(key_points, list) else [],
        india_impact=str(data.get("india_impact") or NOT_ASSESSED),
        category=category,
        # The model occasionally returns a 0-10 scale despite the instruction.
        significance=max(1, min(5, significance)),
        affected_sectors=[str(s) for s in sectors] if isinstance(sectors, list) else [],
    )


def heuristic_briefing(doc: RawDocument) -> Briefing:
    """Build a briefing with no model call at all.

    This is what `--no-llm` produces. It is a *listing*, not an assessment:
    you get the document, its category and a crude ranking, but nothing that
    requires reading the text — no impact analysis, no key points. The
    `india_impact` field says so explicitly rather than leaving a plausible
    blank that could be mistaken for "no impact".
    """
    text = doc.searchable_text()
    mentions_india = bool(_term_hits(text, INDIA_TERMS))
    category = heuristic_category(doc)

    # Crude but defensible: naming India outranks a bare trade action, and a
    # duty or export-control action outranks a procedural notice.
    if mentions_india:
        significance = 4
    elif category in (Category.AD_CVD, Category.EXPORT_CONTROL, Category.TARIFF):
        significance = 3
    else:
        significance = 2

    impact = (
        "Mentions India directly — read the source document."
        if mentions_india
        else "No direct India reference found in the title or abstract."
    )

    return Briefing(
        document_hash=doc.content_hash,
        headline=doc.title[:200],
        context=(doc.abstract or doc.title)[:600],
        key_points=[],
        india_impact=f"{NOT_ANALYSED} {impact}",
        category=category,
        significance=significance,
        affected_sectors=[],
    )


async def summarize(doc: RawDocument, llm: LLMClient) -> Briefing:
    user = (
        f"Title: {doc.title}\n"
        f"Source: {doc.source.label}\n"
        f"Agencies: {', '.join(doc.agencies) or 'unknown'}\n"
        f"Type: {doc.doc_type or 'unknown'}\n"
        f"Published: {doc.published.isoformat()}\n"
        f"URL: {doc.url}\n"
        f"Abstract: {(doc.abstract or '(none)')[:3000]}"
    )
    raw = await llm.complete(SUMMARIZE_SYSTEM, user)
    return _coerce_briefing(raw, doc)
