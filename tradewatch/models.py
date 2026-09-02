"""Domain models.

Every model is a pydantic type so that malformed data fails at the boundary
rather than three stages downstream.

The one design decision worth calling out is `content_hash`: it is derived
from title, publication date and abstract — deliberately not the URL. The
same USTR release republished by two sources has two URLs but one hash, so
deduplication collapses it to a single entry.
"""

from __future__ import annotations

import hashlib
from datetime import date
from enum import Enum

from pydantic import BaseModel, Field


class SourceType(str, Enum):
    FEDERAL_REGISTER = "federal_register"
    USTR = "ustr"
    COMMERCE = "commerce"
    PIB = "pib"

    @property
    def label(self) -> str:
        return _SOURCE_LABELS[self]


_SOURCE_LABELS = {
    SourceType.FEDERAL_REGISTER: "Federal Register",
    SourceType.USTR: "USTR",
    SourceType.COMMERCE: "Commerce Department",
    SourceType.PIB: "PIB India",
}


class Category(str, Enum):
    AD_CVD = "ad_cvd"
    TARIFF = "tariff"
    IPR = "ipr"
    EXPORT_CONTROL = "export_control"
    TRADE_AGREEMENT = "trade_agreement"
    TECH_POLICY = "tech_policy"
    INVESTMENT = "investment"
    OTHER = "other"

    @property
    def label(self) -> str:
        return _CATEGORY_LABELS[self]


_CATEGORY_LABELS = {
    Category.AD_CVD: "Anti-Dumping / Countervailing Duty",
    Category.TARIFF: "Tariff",
    Category.IPR: "Intellectual Property",
    Category.EXPORT_CONTROL: "Export Control",
    Category.TRADE_AGREEMENT: "Trade Agreement",
    Category.TECH_POLICY: "Technology Policy",
    Category.INVESTMENT: "Investment",
    Category.OTHER: "Other",
}


class RawDocument(BaseModel):
    """A document as ingested, before any model has looked at it."""

    source: SourceType
    external_id: str
    title: str
    url: str
    published: date
    abstract: str | None = None
    agencies: list[str] = Field(default_factory=list)
    doc_type: str | None = None

    def searchable_text(self) -> str:
        """Lowercased haystack for the keyword prefilter."""
        parts = [
            self.title,
            self.abstract or "",
            " ".join(self.agencies),
            self.doc_type or "",
        ]
        return " ".join(parts).lower()

    @property
    def content_hash(self) -> str:
        """Identity of the *content*, not of the URL it arrived at."""
        payload = "|".join(
            [self.title.strip(), self.published.isoformat(), (self.abstract or "").strip()]
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class RelevanceVerdict(BaseModel):
    """Stage-two output. Mutable: `assess` may veto on the score threshold."""

    is_relevant: bool
    score: float
    category: Category
    reason: str = ""


class Briefing(BaseModel):
    """The structured note produced for one relevant document.

    The shape mirrors a government briefing note — context, key points,
    impact assessment, significance — rather than a generic summary, because
    that structure is what makes the output usable for decisions.
    """

    document_hash: str
    headline: str
    context: str
    key_points: list[str] = Field(default_factory=list)
    india_impact: str
    category: Category
    significance: int = Field(ge=1, le=5)
    affected_sectors: list[str] = Field(default_factory=list)


class DigestEntry(BaseModel):
    document: RawDocument
    briefing: Briefing


class Digest(BaseModel):
    digest_date: date
    entries: list[DigestEntry] = Field(default_factory=list)
    documents_scanned: int = 0
    documents_filtered: int = 0

    def by_significance(self) -> list[DigestEntry]:
        """Most significant first; ties broken by publication date, newest up."""
        return sorted(
            self.entries,
            key=lambda e: (e.briefing.significance, e.document.published),
            reverse=True,
        )
