"""Response models for the read API.

These are the contract. They are deliberately *not* the pipeline's domain
models: `RawDocument` and `Briefing` describe what the pipeline works with,
and re-exporting them would tie the frontend to internal shapes that change
for reasons the UI does not care about. Two of the fields below (`source`,
`category`) also arrive as enums and leave as slug plus human label, which is
the sort of translation a contract exists to do.

One field the spec asked for is missing on purpose. There is no `confidence`:
the relevance score is computed during classification and never persisted, so
the API cannot report it without the pipeline changing. What is stored, and
what actually ranks a document, is `significance` — 1 to 5, assigned by the
briefing step. Reporting that instead keeps the read path read-only.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class CategoryCount(BaseModel):
    """One filterable category, with how many briefed documents it holds."""

    slug: str
    label: str
    count: int


class DocumentSummary(BaseModel):
    """A document as it appears in a list.

    No briefing body. A list view renders a headline and some metadata, so
    shipping the full note for every row would multiply the payload for text
    nobody reads until they click. The detail endpoint carries it instead.
    """

    id: str
    title: str
    url: str
    source: str
    source_label: str
    published: date
    category: str
    category_label: str
    significance: int = Field(ge=1, le=5)
    excerpt: str = Field(
        description="The briefing headline — one line, already written to stand alone."
    )


class DocumentDetail(DocumentSummary):
    """A single document with its full briefing note.

    Extends the summary rather than redefining it, so the fields a list and a
    detail view share cannot drift apart.
    """

    abstract: str | None = None
    agencies: list[str] = Field(default_factory=list)
    doc_type: str | None = None

    context: str
    key_points: list[str] = Field(default_factory=list)
    india_impact: str
    affected_sectors: list[str] = Field(default_factory=list)
    briefed_on: date


class DocumentPage(BaseModel):
    """A page of results, plus the total the filter matched.

    `total` is the count before limit and offset, which is what a pager needs
    and what the length of `items` cannot tell it.
    """

    items: list[DocumentSummary]
    total: int
