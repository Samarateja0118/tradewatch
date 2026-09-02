"""Relevance filtering.

Two stages, deliberately. The Federal Register publishes hundreds of
documents a day; sending all of them to an LLM would be slow and expensive
for no benefit. So a cheap deterministic prefilter removes the obvious
noise, and only survivors get a model call.

This is the main cost lever in the pipeline: the prefilter typically drops
80-90% of candidates at zero marginal cost.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Protocol

from ..models import Category, RawDocument, RelevanceVerdict

log = logging.getLogger(__name__)

# Terms that make a document worth a model call at all.
INDIA_TERMS = frozenset(
    {"india", "indian", "new delhi", "bharat", "mumbai", "bengaluru"}
)

# Grouped so that spelling variants and inflections of one concept count
# once. "antidumping duties" is a single signal, not two; treating it as two
# used to trip the two-term gate on its own.
TRADE_TERM_GROUPS: dict[str, frozenset[str]] = {
    "antidumping": frozenset({"antidumping", "anti-dumping"}),
    "countervailing": frozenset({"countervailing"}),
    "tariff": frozenset({"tariff", "tariffs"}),
    "duty": frozenset({"duty", "duties"}),
    "trade_agreement": frozenset({"trade agreement", "free trade"}),
    # Bare "import"/"export" match almost any Federal Register notice, so
    # only the policy-instrument phrasings count.
    "import_measure": frozenset({"import duty", "import restriction", "import ban"}),
    "export_measure": frozenset({"export control", "export restriction", "export ban"}),
    "customs": frozenset({"customs"}),
    "wto": frozenset({"wto"}),
    "section_action": frozenset({"section 301", "section 232", "section 122"}),
    "quota": frozenset({"quota", "quotas"}),
    "safeguard": frozenset({"safeguard", "safeguards"}),
    "ustr": frozenset({"trade representative"}),
    "market_access": frozenset({"market access"}),
    "rules_of_origin": frozenset({"rules of origin"}),
    "gsp": frozenset({"generalized system of preferences"}),
}

TRADE_TERMS = frozenset().union(*TRADE_TERM_GROUPS.values())

TECH_TERMS = frozenset(
    {
        "semiconductor",
        "artificial intelligence",
        "export control",
        "critical mineral",
        "supply chain",
        "biotechnology",
        "quantum",
        "data center",
        "entity list",
    }
)

_WORD_RE = re.compile(r"[a-z][a-z\-]+")


def _term_hits(text: str, terms: frozenset[str]) -> set[str]:
    """Match multi-word terms by substring, single words by token."""
    hits: set[str] = set()
    tokens = set(_WORD_RE.findall(text))
    for term in terms:
        if " " in term or "-" in term:
            if term in text:
                hits.add(term)
        elif term in tokens:
            hits.add(term)
    return hits


def _trade_concepts(text: str) -> set[str]:
    """Distinct trade concepts present, collapsing variants of the same one."""
    hits = _term_hits(text, TRADE_TERMS)
    return {
        concept
        for concept, variants in TRADE_TERM_GROUPS.items()
        if hits & variants
    }


def prefilter(doc: RawDocument) -> bool:
    """Cheap deterministic gate. True means 'worth a model call'.

    A document passes if it mentions India, or if it is squarely about trade
    or technology policy (which may affect India even without naming it —
    a global tariff action, for instance). "Squarely" means two distinct
    concepts, so a single passing mention of one term is not enough.
    """
    text = doc.searchable_text()
    if _term_hits(text, INDIA_TERMS):
        return True
    trade = _trade_concepts(text)
    tech = _term_hits(text, TECH_TERMS)
    return len(trade) >= 2 or len(tech) >= 2 or bool(trade and tech)


def heuristic_category(doc: RawDocument) -> Category:
    """Best-guess category without a model call. Used as a fallback."""
    text = doc.searchable_text()
    if _term_hits(text, frozenset({"antidumping", "anti-dumping", "countervailing"})):
        return Category.AD_CVD
    if "export control" in text or "entity list" in text:
        return Category.EXPORT_CONTROL
    if _term_hits(text, frozenset({"tariff", "duty", "duties", "safeguard"})):
        return Category.TARIFF
    if _term_hits(text, frozenset({"patent", "copyright", "trademark", "special 301"})):
        return Category.IPR
    if "trade agreement" in text or "free trade" in text:
        return Category.TRADE_AGREEMENT
    if _term_hits(text, TECH_TERMS):
        return Category.TECH_POLICY
    return Category.OTHER


class LLMClient(Protocol):
    """Minimal interface so the pipeline can be tested without network."""

    async def complete(self, system: str, user: str) -> str: ...


RELEVANCE_SYSTEM = """You assess whether US government documents matter to \
India-US trade and technology relations.

Respond with ONLY a JSON object, no prose and no markdown fences:
{"is_relevant": bool, "score": float 0-1, "category": string, "reason": string}

category must be one of: ad_cvd, tariff, ipr, export_control, \
trade_agreement, tech_policy, investment, other.

Score 0.8+ only for direct, material impact on Indian exporters, Indian \
firms, or the bilateral relationship. Routine administrative notices that \
merely mention India score low."""


# Marks a verdict the model did not actually produce. Such a verdict is
# exempt from the score threshold — see `assess`.
PARSE_FAILED = "parse_failed"


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


def _coerce_verdict(raw: str, fallback: Category) -> RelevanceVerdict:
    """Parse model output defensively; never let a bad response crash a run."""
    candidate = _extract_json_object(raw)
    try:
        if candidate is None:
            raise json.JSONDecodeError("no JSON object found", raw, 0)
        data = json.loads(candidate)
    except json.JSONDecodeError:
        log.warning("Relevance response was not JSON; keeping for human review")
        return RelevanceVerdict(
            is_relevant=True, score=0.5, category=fallback, reason=PARSE_FAILED
        )

    try:
        category = Category(str(data.get("category", "other")).lower())
    except ValueError:
        category = fallback

    return RelevanceVerdict(
        is_relevant=bool(data.get("is_relevant", False)),
        score=max(0.0, min(1.0, float(data.get("score", 0.0)))),
        category=category,
        reason=str(data.get("reason", ""))[:300],
    )


async def assess(
    doc: RawDocument, llm: LLMClient, *, threshold: float = 0.55
) -> RelevanceVerdict:
    """Stage two: ask the model whether this actually matters."""
    user = (
        f"Title: {doc.title}\n"
        f"Agencies: {', '.join(doc.agencies) or 'unknown'}\n"
        f"Type: {doc.doc_type or 'unknown'}\n"
        f"Abstract: {(doc.abstract or '(none)')[:1500]}"
    )
    raw = await llm.complete(RELEVANCE_SYSTEM, user)
    verdict = _coerce_verdict(raw, heuristic_category(doc))

    # A parse failure carries no real score, so the threshold must not be
    # applied to it — the 0.5 placeholder sits below the default cutoff of
    # 0.55, which would silently drop exactly the documents a human should
    # look at.
    if verdict.reason != PARSE_FAILED and verdict.score < threshold:
        verdict.is_relevant = False
    return verdict
